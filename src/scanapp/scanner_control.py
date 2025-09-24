import os
import threading
import time
from enum import Enum
from typing import Callable, Generator

from PIL import Image
from RPi import GPIO

from scanapp.ds_driver import DSDriver, SSPRequest, XSCRequest

PIN_ONOFF = 26
PIN_BUTTON = 16
PIN_PAPER = 19
PIN_MOTOR_AWAKE = 12
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
# Maximum duration for a long scan, before the scanner needs an "end_paper of paper"
SCAN_MAX_DURATION_LONG = 30
# Time after starting the scan, when to enable the motor
MOTOR_WAKE_START_TIME = 1.4
# Time after starting the scan, when to disable the motor
MOTOR_SLEEP_START_TIME = SCAN_MAX_DURATION + 0.2

DPI = 100


class ScannerState(Enum):
    PowerDown = 0
    PowerSaving = 1
    StartingUp = 5
    ScanStarting = 30
    ScanRunning = 31
    ScanReceiving = 32
    Ready = 10
    Paperjam = 20


class Waiter:
    def __init__(self):
        self._t = threading.Thread(target=self._thread)
        self._lock = threading.Lock()
        self._e = threading.Condition(self._lock)
        self._restart = threading.Condition(self._lock)
        self._exit = False
        self._f = None
        self._to = 0
        self._t.start()

    def _thread(self):
        while True:
            with self._lock:
                self._e.wait()
                if self._exit:
                    break
                if self._restart.wait(self._to):
                    if self._exit:
                        break
                    continue
                f = self._f
                self._f = None
            f()

    def delay(self, t: float, f: Callable[[], None]):
        with self._lock:
            assert self._f is None, "Can only handle one parallel delay"
            self._to = t
            self._f = f
            self._e.notify()

    def stop(self):
        with self._lock:
            assert self._f is None, "Can only handle one parallel delay"
            self._to = 0
            self._f = None
            self._restart.notify()

    def shutdown(self):
        if self._exit:
            return
        with self._lock:
            self._exit = True
            self._restart.notify()
            self._e.notify()
            self._t.join()


class Timer:
    def __init__(self, f: Callable[[], None]):
        self._t = threading.Thread(target=self._thread)
        self._lock = threading.Lock()
        self._e = threading.Condition(self._lock)
        self._f = f
        self._exit = False
        self._restart = threading.Condition(self._lock)
        self._to = 0
        self._t.start()

    def _thread(self):
        while True:
            with self._lock:
                self._e.wait()
                if self._exit:
                    break
                if self._restart.wait(self._to):
                    if self._exit:
                        break
                    continue
            self._f()

    def start(self, t: float):
        with self._lock:
            self._to = t
            self._restart.notify()
            self._e.notify()

    def stop(self):
        with self._lock:
            self._restart.notify()

    def shutdown(self):
        if self._exit:
            return
        with self._lock:
            self._exit = True
            self._restart.notify()
            self._e.notify()
            self._t.join()


def read_file_by_lines(f: int) -> Generator[bytes, None, None]:
    buf = []
    while True:
        r = os.read(f, 1024)
        if not r:
            break
        buf.append(r)
        if b"\n" in r:
            lines = b"".join(buf).split(b"\n")
            buf.clear()
            buf.append(lines[-1])
            yield from lines[:-1]


def read_file_raw(f: int) -> bytes:
    buf = []
    while True:
        r = os.read(f, 1024 * 64)
        if not r:
            break
        buf.append(r)
    return b"".join(buf)


class ScannerControl:
    _state: ScannerState = ScannerState.PowerDown

    state_change: Callable[[ScannerState], None]
    # Scanner is ready to scan
    scanner_ready: Callable[[], None]
    # Scanner is not ready to scan
    scanner_shutdown: Callable[[], None]

    # Scanner is starting to scan
    scanner_starting: Callable[[], None]
    # Scanner is pulling through data and scanning
    scanner_running: Callable[[float], None]
    # Scanner is currently receiving the data
    scanner_receiving: Callable[[], None]
    # One of the following three will end the scan:
    # Result is the Image
    scanner_success: Callable[[Image.Image], None]
    # Scanner has jammed :(
    scanner_jam: Callable[[], None]
    # Scanner has no paper (internal error!)
    scanner_no_paper: Callable[[], None]

    def __init__(self):
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(PIN_ONOFF, GPIO.OUT)
        GPIO.setup(PIN_BUTTON, GPIO.OUT)
        GPIO.setup(PIN_PAPER, GPIO.OUT)
        GPIO.setup(PIN_MOTOR_AWAKE, GPIO.OUT)
        GPIO.output(PIN_ONOFF, False)
        GPIO.output(PIN_BUTTON, False)
        GPIO.output(PIN_PAPER, False)
        GPIO.output(PIN_MOTOR_AWAKE, False)
        self._waiter = Waiter()
        self._waiter2 = Waiter()
        self._sleep_timer = Timer(self._on_power_saving)

    def startup(self):
        """
        (asynchronously)
        Power up the scanner if it is not.
        If it is in paperjam mode, request reset.
        If it is already started up, do nothing.
        Triggers user_inser_scan_now when ready to accept paper.
        Triggers paper_jam when scanner is jammed (will shut down scanner and needs to be called again).
        """
        if self._state == ScannerState.PowerDown:
            print(".startup() -> power_on")
            self._power_on()
        elif self._state == ScannerState.PowerSaving:
            print(".startup() -> resume_from_powersaving")
            self._resume_from_powersaving()
        else:
            print(".startup() -> noop")
            # It's already ready!
            self.scanner_ready()

    def can_scan(self) -> bool:
        """Ensures that the scanner is ready and can scan now."""
        return self._state == ScannerState.Ready

    def shutdown(self):
        """Shuts down the scanner (asynchronously)."""
        print(".shutdown()")
        self._power_off()

    def end(self):
        print(".end()")
        self._waiter.shutdown()
        self._waiter2.shutdown()
        self._sleep_timer.shutdown()

    def reset(self):
        """Resets the scanner in case of error"""
        self._power_off()
        self._waiter.delay(RESTART_DELAY, self._power_on)

    def _set_state(self, state: ScannerState):
        print(f"._set_state({state!r})")
        self._state = state
        self.state_change(state)

    def _on_power_saving(self):
        print("._on_power_saving()")
        self._set_state(ScannerState.PowerSaving)
        self.scanner_shutdown()

    def _on_powered_on(self, *_):
        print("._powered_on()")
        self._sleep_timer.start(POWERSAVING_TIMEOUT)
        self._set_state(ScannerState.Ready)
        self.scanner_ready()

        print("Initializing USB driver")
        self.drv = DSDriver()

    def _power_on(self):
        print("._power_on()")
        self._sleep_timer.stop()
        GPIO.output(PIN_ONOFF, True)
        GPIO.output(PIN_MOTOR_AWAKE, True)
        self._set_state(ScannerState.StartingUp)
        self._waiter.delay(STARTUP_DURATION, self._on_powered_on)
        self._waiter2.delay(0.1, self._push_button)

    def _power_off(self):
        print("._power_off()")
        self._sleep_timer.stop()
        self._waiter.stop()
        self._waiter2.stop()

        if self.drv is not None:
            self.drv.close()
            self.drv = None

        GPIO.output(PIN_MOTOR_AWAKE, False)
        GPIO.output(PIN_ONOFF, False)
        GPIO.output(PIN_BUTTON, False)
        GPIO.output(PIN_PAPER, False)
        if self._state != ScannerState.PowerDown:
            self._set_state(ScannerState.PowerDown)
            self.scanner_shutdown()

    def _push_button(self):
        print("._push_button()")
        # "Push" the button once
        GPIO.output(PIN_BUTTON, True)
        time.sleep(0.1)
        GPIO.output(PIN_BUTTON, False)

    def _resume_from_powersaving(self):
        print("._resume_from_powersaving()")
        self._sleep_timer.stop()
        self._push_button()
        self._waiter.delay(STARTUP_RESUME_DURATION, self._on_powered_on)

    def scan(self, long: bool):
        """Starts scanning"""
        print(".scan()")
        assert self.can_scan()
        self._set_state(ScannerState.ScanStarting)
        t = threading.Thread(
            target=self._scan,
            args=(SCAN_MAX_DURATION_LONG if long else SCAN_MAX_DURATION,),
        )
        t.start()

    def scan_stop(self):
        """Stop scanning"""
        print(".scan_stop()")
        GPIO.output(PIN_PAPER, False)

    drv: DSDriver | None = None

    def _scan(self, duration: float = SCAN_MAX_DURATION):
        print("._scan()")
        assert self.drv is not None, "Driver not initialized"
        self.scanner_starting()
        start = time.time()
        # GPIO.output(PIN_MOTOR_AWAKE, False)

        t_barrier = threading.Barrier(2)
        t_abort = threading.Event()

        def end_paper():
            nonlocal start
            # Synchronize the start
            t_barrier.wait()
            t_abort.wait(duration)
            GPIO.output(PIN_PAPER, False)
            print(f"Paper=False after {time.time() - start}sec")
            start = time.time()

            self._set_state(ScannerState.ScanReceiving)
            self.scanner_receiving()

        t_end_paper = threading.Thread(target=end_paper)

        t_end_paper.start()
        print("Threads started")

        print("Setting paper=True")
        GPIO.output(PIN_PAPER, True)
        time.sleep(0.5)

        # Ensure thread is started
        print("Sync")
        t_barrier.wait()

        try:
            if duration > SCAN_MAX_DURATION:
                long = "ON"
            else:
                long = "OFF"
            self.drv.set_parameters(SSPRequest(RESO=(150, 150), LONG=long, AREA="OVER"))
            self.scanner_running(duration)
            page = None
            for page in self.drv.scan(
                XSCRequest(
                    RESO=(150, 150),
                    AREA=(0, 0, 1294, 1650),
                )
            ):
                pass
            print(f"Done after {time.time() - start}s")
        finally:
            # Finish everything
            t_abort.set()
            t_end_paper.join()
            GPIO.output(PIN_PAPER, False)

        print(f"Duration: {time.time() - start}sec")
        self._set_state(ScannerState.Ready)
        if page is not None:
            self.scanner_success(page)
        else:
            self.scanner_no_paper()


if __name__ == "__main__":
    print("Starting up scanner")
    e = threading.Event()
    n = 0
    sc = ScannerControl()

    def save(img: Image.Image):
        global n
        img.save(f"last_{n}.jpg", quality=90)
        n += 1
        e.set()

    sc.state_change = lambda state: print(f"State: {state}")
    sc.scanner_ready = lambda: e.set()
    sc.scanner_shutdown = lambda: e.set()
    sc.scanner_starting = lambda: None
    sc.scanner_running = lambda t: None
    sc.scanner_receiving = lambda: None
    sc.scanner_success = save
    sc.scanner_jam = lambda: e.set()
    sc.scanner_no_paper = lambda: e.set()
    sc.startup()
    e.wait()
    e.clear()
    sc.scan(False)
    e.wait()
    e.clear()
    sc.scan(False)
    e.wait()
    e.clear()
    sc.shutdown()
    e.wait()
    # Shutdown for real
    sc.end()
