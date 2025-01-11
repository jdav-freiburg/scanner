from RPi import GPIO
from typing import Callable, Generator
import subprocess
import time
import threading
import selectors
import os
from enum import Enum


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
SCAN_MAX_DURATION = 10.5
# Time after starting the scan, when to enable the motor
#MOTOR_WAKE_START_TIME = 1.85
MOTOR_WAKE_START_TIME1 = 1.0
MOTOR_WAKE_START_TIME2 = 0.8
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
        if b'\n' in r:
            lines = b''.join(buf).split(b'\n')
            buf.clear()
            buf.append(lines[-1])
            yield from lines[:-1]


def read_file_raw(f: int) -> bytes:
    buf = []
    while True:
        r = os.read(f, 1024*64)
        if not r:
            break
        buf.append(r)
    return b''.join(buf)


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
    scanner_running: Callable[[], None]
    # Scanner is currently receiving the data
    scanner_receiving: Callable[[], None]
    # One of the following three will end the scan:
    # Result is the bytes
    scanner_success: Callable[[bytes], None]
    # Scanner has jammed :(
    scanner_jam: Callable[[], None]
    # Scanner has no paper (internal error!)
    scanner_no_paper: Callable[[], None]

    def __init__(self):
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(PIN_ONOFF, GPIO.OUT)
        GPIO.setup(PIN_BUTTON, GPIO.OUT)
        GPIO.setup(PIN_PAPER, GPIO.OUT)
        GPIO.setup(PIN_MOTOR_SLEEP, GPIO.OUT)
        GPIO.output(PIN_ONOFF, False)
        GPIO.output(PIN_BUTTON, False)
        GPIO.output(PIN_PAPER, False)
        GPIO.output(PIN_MOTOR_SLEEP, False)
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

    def _power_on(self):
        print("._power_on()")
        self._sleep_timer.stop()
        GPIO.output(PIN_ONOFF, True)
        GPIO.output(PIN_MOTOR_SLEEP, True)
        self._set_state(ScannerState.StartingUp)
        self._waiter.delay(STARTUP_DURATION, self._on_powered_on)
        self._waiter2.delay(0.1, self._push_button)

    def _power_off(self):
        print("._power_off()")
        self._sleep_timer.stop()
        self._waiter.stop()
        self._waiter2.stop()
        GPIO.output(PIN_MOTOR_SLEEP, False)
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

    def scan(self):
        """Starts scanning"""
        print(".scan()")
        assert self.can_scan()
        self._set_state(ScannerState.ScanStarting)
        t = threading.Thread(target=self._scan)
        t.start()

    def _scan(self):
        print("._scan()")
        self.scanner_starting()
        jam = False
        no_paper = False
        res_data = b''
        start = time.time()
        GPIO.output(PIN_MOTOR_SLEEP, False)

        t_barrier = threading.Barrier(6)
        t_process_signal = threading.Event()
        t_scanning_signal = threading.Event()
        t_abort = threading.Event()
        def end_paper():
            nonlocal start
            # Synchronize the start
            t_barrier.wait()
            # It's now ready to start the sleep most "precisely"
            t_scanning_signal.wait()
            t_abort.wait(SCAN_MAX_DURATION)
            GPIO.output(PIN_PAPER, False)
            print(f"Paper=False after {time.time()-start}sec")
            start = time.time()

            self._set_state(ScannerState.ScanReceiving)
            self.scanner_receiving()

        def start_motor():
            # Synchronize the start
            t_barrier.wait()
            # It's now ready to start the sleep most "precisely"
            t_scanning_signal.wait()
            t_abort.wait(1.4)
            GPIO.output(PIN_MOTOR_SLEEP, True)
            # t_abort.wait(1)
            # GPIO.output(PIN_MOTOR_SLEEP, False)
            # t_abort.wait(MOTOR_WAKE_START_TIME2)
            # GPIO.output(PIN_MOTOR_SLEEP, True)
            print(f"Motor=Sleep after {time.time()-start}sec")            

        def stop_motor():
            # Synchronize the start
            t_barrier.wait()
            # It's now ready to start the sleep most "precisely"
            t_scanning_signal.wait()
            t_abort.wait(MOTOR_SLEEP_START_TIME)
            GPIO.output(PIN_MOTOR_SLEEP, False)
            print(f"Motor=Sleep after {time.time()-start}sec")            

        def read_data_fn():
            nonlocal res_data
            # Synchronize the start
            t_barrier.wait()
            t_process_signal.wait()
            res_data = read_file_raw(read_data)
        
        def read_info_fn():
            nonlocal no_paper, jam, start
            # Synchronize the start
            t_barrier.wait()
            t_process_signal.wait()
            for line in read_file_by_lines(read_info):
                if b'sane_start(' in line:
                    # Scanner is now starting, notify the thread
                    start = time.time()
                    t_scanning_signal.set()
                    print("Scanner Start, start paper timeout")
                    self._set_state(ScannerState.ScanRunning)
                    self.scanner_running()
                elif b'sane_close(' in line:
                    # Scanner has finished
                    print("Scanner Close")
                elif b"Document feeder out of documents" in line:
                    no_paper = True
                elif b"Document feeder jammed" in line:
                    jam = True

        t_timeout = threading.Thread(target=end_paper)
        t_read_data = threading.Thread(target=read_data_fn)
        t_read_info = threading.Thread(target=read_info_fn)
        t_start_motor = threading.Thread(target=start_motor)
        t_stop_motor = threading.Thread(target=stop_motor)

        t_timeout.start()
        t_read_data.start()
        t_read_info.start()
        t_start_motor.start()
        t_stop_motor.start()

        print("Threads started")

        print("Setting paper=True")
        GPIO.output(PIN_PAPER, True)
        time.sleep(0.5)
        
        # Ensure thread is started
        print("Sync")
        t_barrier.wait()

        try:
            read_data, write_data = os.pipe()
            read_info, write_info = os.pipe()
            # Scan
            with subprocess.Popen(
                ["sudo", "chroot", "/opt/scanberryd-amd64/", "bash", "-c", f"SANE_DEBUG_DLL=255 scanimage --format=png --resolution={DPI}"],
                stdout=write_data,
                stderr=write_info,
                close_fds=True,
            ) as proc:
                # Activate the readers
                t_process_signal.set()
                # This will wait until the process has finished
            print(f"Done after {time.time() - start}s")
        finally:
            # Finish everything
            os.close(write_data)
            os.close(write_info)
            t_process_signal.set()
            t_scanning_signal.set()
            t_abort.set()
            t_timeout.join()
            t_read_data.join()
            t_read_info.join()
            t_stop_motor.join()

        print(f"Duration: {time.time() - start}sec")
        if not jam and not no_paper:
            # Did it work? :)
            # Contains the png file
            assert len(res_data) > 0, proc.stderr.decode()
            assert res_data[:4] == b"\x89PNG"
            print(f"Received data: {len(res_data)}b")
            self._set_state(ScannerState.Ready)
            self.scanner_success(res_data)
        elif jam:
            self._set_state(ScannerState.Paperjam)
            self.scanner_jam()
        elif no_paper:
            self._set_state(ScannerState.Ready)
            self.scanner_no_paper()


if __name__ == '__main__':
    print("Starting up scanner")
    e = threading.Event()
    n = 0
    sc = ScannerControl()
    
    def save(data: bytes):
        global n
        with open(f"last_{n}.png", 'wb') as wf:
            wf.write(data)
        n += 1
        e.set()
    
    sc.state_change = lambda state: print(f"State: {state}")
    sc.scanner_ready = lambda: e.set()
    sc.scanner_shutdown = lambda: e.set()
    sc.scanner_starting = lambda: None
    sc.scanner_running = lambda: None
    sc.scanner_receiving = lambda: None
    sc.scanner_success = save
    sc.scanner_jam = lambda: e.set()
    sc.scanner_no_paper = lambda: e.set()
    sc.startup()
    e.wait()
    e.clear()
    sc.scan()
    e.wait()
    e.clear()
    sc.scan()
    e.wait()
    e.clear()
    sc.shutdown()
    e.wait()
    # Shutdown for real
    sc.end()
