import struct
import threading
import time
from dataclasses import asdict, dataclass
from io import BytesIO
from typing import Generator, Literal

import usb.core
import usb.util
from PIL import Image
from RPi import GPIO

PIN_ONOFF = 26
PIN_BUTTON = 16
PIN_PAPER = 19
PIN_MOTOR_SLEEP = 12

# 10min is default power saving timeout
POWERSAVING_TIMEOUT = 10 * 60
# About 4sec for booting from powerdown state
STARTUP_RESUME_DURATION = 4
# About 7sec for startup from no power
STARTUP_DURATION = 7
# Delay until starting the scanner again
RESTART_DELAY = 1
# Maximum duration for a scan, before the scanner needs an "end_paper of paper"
SCAN_MAX_DURATION = 10
# Maximum duration for a long scan, before the scanner needs an "end_paper of paper". Approximately 3*SCAN_MAX_DURATION
SCAN_MAX_DURATION_LONG = 3 * SCAN_MAX_DURATION
# Time after starting the scan, when to enable the motor
MOTOR_WAKE_START_TIME = 1.0


@dataclass
class SerializableScanParam:
    def to_bytes(self):
        def _as_bytes(val):
            if isinstance(val, bytes):
                return val
            if isinstance(val, tuple):
                return b",".join(_as_bytes(v) for v in val)
            return str(val).encode()

        return b"".join(
            key.encode() + b"=" + _as_bytes(value) + b"\n"
            for key, value in asdict(self).items()
            if value is not None
        )


@dataclass
class XSCRequest(SerializableScanParam):
    RESO: tuple[int, int]
    AREA: tuple[int, int, int, int]
    MODE: Literal["NORMAL"] = "NORMAL"


@dataclass
class SSPRequest(SerializableScanParam):
    # Resolution
    RESO: tuple[
        Literal["AUTO", 100, 150, 200, 300, 600, 1200],
        Literal["AUTO", 100, 150, 200, 300, 600, 1200],
    ]
    OS: str = "RPI"
    # Feed source
    PSRC: Literal["ADF", "FB", "AUTO"] = "AUTO"
    # Duplex
    DPLX: Literal["ON", "OFF"] = "OFF"
    # Paged or single page
    PAGE: Literal["0", "1"] = "0"
    # Color mode
    CLR: Literal["TEXT", "ERRDIF", "C24BIT", "GRAY256", "AUTO"] = "C24BIT"
    # Area
    AREA: Literal["NORMAL", "OVER", "AUTO"] | int = "OVER"
    # Margin
    MRGN: tuple[int, int, int, int] = (0, 0, 0, 0)
    # Contrast
    CONT: int = 50
    # Brightness
    BRIT: int = 50
    # Autocolor Level
    ATCL: int | None = None
    # Threshold?
    THRS: Literal["AUTO"] | int | None = None
    # Compress
    COMP: Literal["TEXT", "NONE", "ERRDIF", "JPEG", "RLENGTH", ""] = "JPEG"
    # Sample factor
    JSF: Literal["444", "400", "420", "422"] = "420"
    # Compress ratio
    RATE: Literal[0, 1, 2] = 0
    # Long page
    LONG: Literal["ON", "OFF"] = "OFF"
    # Doublefeed detection
    DTDF: Literal["ON", "OFF"] = "OFF"
    # Doublefeed detection action
    OPDF: Literal["STOP", "CONT"] | None = None
    # Remove blank page
    RMBP: Literal["ON", "OFF"] | int = "OFF"
    # Gamma
    GMMA: Literal["OFF"] | int = "OFF"
    # Tone
    TONE: Literal["ON", "OFF"] = "OFF"
    # Continue scan
    ATCN: Literal["ON", "OFF"] = "OFF"
    # Continue scan, Scan delay, <=5
    ATFD: int | None = None


class DSDriver:
    dev: usb.core.Device

    def __init__(self):
        # find our device
        self.dev = usb.core.find(idVendor=0x04F9, idProduct=0x0468)

        self.aborting = False

        # was it found?
        if self.dev is None:
            raise ValueError("Device not found")

        self.dev.set_configuration()

        self.cfg = self.dev.get_active_configuration()
        print("Configs:", self.cfg)
        # Interface
        self.ctrl_interface = self.cfg[(0, 0)]
        self.user_interface = self.cfg[(1, 0)]

        self.user_write_ep = self.user_interface[0]
        assert self.user_write_ep.bEndpointAddress == 0x04
        self.user_read_ep = self.user_interface[1]
        assert self.user_read_ep.bEndpointAddress == 0x83
    
    def close(self):
        self.dev.finalize()

    def _user_write(self, data: bytes, timeout: int = 1000) -> None:
        print(">>> ", data)
        self.dev.write(0x04, data, timeout)
        # self.user_write_ep.write(data)

    def _user_read(self, size: int, timeout: int = 5000) -> bytes:
        # r = bytes(self.user_read_ep.read(size))
        r = bytes(self.dev.read(0x83, size, timeout))
        print("<<< ", r[:64])
        return r

    def set_source_d(self, source: Literal[b"ADF"] = b"ADF"):
        self._user_write(b"\x1bD\n" + source + b"\n\x80")
        res = self._user_read(1)
        assert res == b"\x80", res

    class ABTHeader:
        # Eject paper
        EJCT: Literal["ALL", "ONE", "NO"]
        # Cancel current scan
        ATCN: str
        # Res 2b: 0x00 0x81

    def abort(self, eject: bool):
        # Handle XSC header
        if eject:
            self._user_write(b"\x1bABT\nEJCT=ONE\n\x80")
        else:
            self._user_write(b"\x1bABT\nEJCT=NO\n\x80")
        res = self._user_read(2)
        assert res == b"\00\x81", res

    def set_source(self, source: Literal[b"ADF"] = b"ADF") -> None:
        self._user_write(b"\x1bS\n" + source + b"\n\x80")
        res = self._user_read(1)
        assert res == b"\x80", res

    def decode_imghdr(self, data: bytes) -> tuple[int, int, int, int, int]:
        pagenum, compression, _, chunk_size, height = struct.unpack("<HBBII", data)
        return pagenum, compression, chunk_size, height

    def scan(self, req: XSCRequest) -> Generator[Image.Image, None, None]:
        # Scanjob
        self._user_write(b"\x1bXSC\n" + req.to_bytes() + b"\n\x80")
        self.aborting = False

        img_data = []
        while True:
            # Receive a response header
            try:
                packet = self._user_read(1024, 100)
            except usb.core.USBTimeoutError:
                if self.aborting:
                    print("Aborting softly")
                    self._user_write(b"\x1bABT\nEJCT=NO\n\x80")
                    self.aborting = False
                continue
            cmd = packet[0]
            if cmd == 0x00:
                detail = packet[1]
                if detail in (0x01, 0x02):
                    pagenum, compression, chunk_size, height = self.decode_imghdr(packet[2:])
                    print(
                        f"Chunk package pagenum={pagenum} compression={compression} chunk_size={chunk_size} height={height}"
                    )
                    img_data.append(self._user_read(chunk_size))
                    if height > 0:
                        img = Image.open(BytesIO(b"".join(img_data)))
                        img_data.clear()
                        img = img.crop((0, 0, img.width, height))
                        yield img
                elif detail == 0x21:
                    # Done
                    pagenum = struct.unpack("<H", packet[2:])
                    print(f"Done pagenum={pagenum}")
                elif detail == 0x23:
                    # Oversize. Buffer overfull?
                    pagenum = struct.unpack("<H", packet[2:])
                    print(f"Oversize? pagenum={pagenum}")
                elif detail == 0x00:
                    # Empty Page
                    assert len(packet) == 2
                    print(f"Empty page")
                elif detail == 0x11:
                    # Whatever case is this?
                    assert len(packet) == 0xC
                    pagenum, width, height = struct.unpack("<HII", packet[2:])
                    print(f"Extra package pagenum={pagenum} width={width} height={height}")
                    # A 0x21 package follows.
                elif detail == 0x20:
                    # Phew, what condition?
                    # Internal: (0x2002, 0x2003, 0x2004)
                    # Maybe this means done?
                    break
                elif detail == 0x41:
                    # Phew, what condition?
                    # internal: 0x4001
                    print(f"Some info code?")
                elif detail == 0x40:
                    # Probably aborted
                    # internal: 0x4002
                    print("Aborted")
                    assert len(packet) == 2
                    # Do not yield any received data.
                    return
                elif detail == 0x51:
                    # error happen
                    print(f"Some error")
                    assert False
                else:
                    assert False, f"Unknown cmd: {packet}"
            elif cmd == 0x01:
                # Done? Or Error?
                print(f"Done? Error? {packet}")
                assert packet == b"\0\0\0\0"
            else:
                # This is unexpected
                assert False, packet

        if len(img_data) > 0:
            yield Image.open(BytesIO(b"".join(img_data)))

    def set_parameters(self, req: SSPRequest):
        self._user_write(b"\x1bSSP\n" + req.to_bytes() + b"\n\x80")
        packet = self._user_read(1024, 1000)
        assert packet[0] == 0x00, packet
        assert len(packet) == 0x26, packet


def dbg_usb_scan():
    drv = DSDriver()
    print("Starting")

    def _scan_thread():
        drv.set_parameters(SSPRequest(RESO=(150, 150), LONG="ON", ATCN="OFF", ATFD=None))
        for page in drv.scan(
            XSCRequest(
                RESO=(150, 150),
                AREA=(0, 0, 1275, 1650),
            )
        ):
            page.save("dump.jpg", quality=90)

    t = threading.Thread(target=_scan_thread)

    start = time.time()
    try:
        t.start()
        t.join()
    except KeyboardInterrupt:
        print("Cancelled, aborting scan immediately")
        drv.aborting = True
        t.join()
    finally:
        print(f"Dur: {time.time() - start}")


def dbg_outer_scan():
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(PIN_ONOFF, GPIO.OUT)
    GPIO.setup(PIN_BUTTON, GPIO.OUT)
    GPIO.setup(PIN_PAPER, GPIO.OUT)
    GPIO.setup(PIN_MOTOR_SLEEP, GPIO.OUT)
    GPIO.output(PIN_ONOFF, False)
    GPIO.output(PIN_BUTTON, False)
    GPIO.output(PIN_PAPER, False)
    GPIO.output(PIN_MOTOR_SLEEP, False)

    print("Power_on")
    GPIO.output(PIN_MOTOR_SLEEP, True)
    GPIO.output(PIN_ONOFF, True)

    try:
        time.sleep(10)
        print("Booted")

        start = time.time()

        drv = None

        t_barrier = threading.Barrier(4)
        t_abort = threading.Event()

        def scan_thread():
            nonlocal drv
            drv = DSDriver()
            # Set parameters
            drv.set_parameters(SSPRequest(RESO=(150, 150), LONG="ON", AREA="OVER"))
            # Synchronize the start
            t_barrier.wait()
            # Now scan and receive the page
            for page in drv.scan(
                XSCRequest(
                    RESO=(150, 150),
                    AREA=(0, 0, 1294, 1650),
                )
            ):
                page.save("dump.jpg", quality=90)

        def end_paper():
            nonlocal start
            # Synchronize the start
            t_barrier.wait()
            t_abort.wait(SCAN_MAX_DURATION_LONG)
            GPIO.output(PIN_PAPER, False)
            print(f"Paper=False after {time.time()-start}sec")
            start = time.time()

        def start_motor():
            # Synchronize the start
            t_barrier.wait()
            t_abort.wait(MOTOR_WAKE_START_TIME)
            GPIO.output(PIN_MOTOR_SLEEP, True)
            print(f"Motor=Wake after {time.time()-start}sec")

        t_paper_out = threading.Thread(target=end_paper)
        t_start_motor = threading.Thread(target=start_motor)
        t_scan = threading.Thread(target=scan_thread)
        try:
            t_paper_out.start()
            t_start_motor.start()
            t_scan.start()

            print("Threads started")

            print("Setting paper=True")
            GPIO.output(PIN_PAPER, True)
            time.sleep(0.5)

            # Ensure thread is started

            input("Press key to scan")
            print("Sync")
            # Synchronize the barriers
            t_barrier.wait()
            # Wait for the scan thread to be done
            t_scan.join()
        except KeyboardInterrupt:
            # On keyboard interrupt, just make the scanner abort.
            print("Set aborting")
            # drv.aborting = True
            GPIO.output(PIN_PAPER, False)
            time.sleep(0.5)
            print("Join scan thread")
            t_scan.join()
        finally:
            print("Set aborting threads")
            t_abort.set()
            t_scan.join()
            t_paper_out.join()
            t_start_motor.join()
    finally:
        GPIO.output(PIN_MOTOR_SLEEP, False)
        GPIO.output(PIN_ONOFF, False)
        GPIO.output(PIN_BUTTON, False)
        GPIO.output(PIN_PAPER, False)
        time.sleep(1)


if __name__ == "__main__":
    dbg_outer_scan()
