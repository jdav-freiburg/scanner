from PIL import Image
from PyQt5.QtCore import QObject, pyqtSignal

from scanapp.scanner_control import ScannerControl, ScannerState


class ScannerController(QObject):
    _state: ScannerState = ScannerState.PowerDown
    _last_image: Image.Image | None = None

    # Called whenever the state changes
    state_change = pyqtSignal(ScannerState)

    # This is called after ensure_startup(), when the scanner is ready to accept paper.
    scanner_ready = pyqtSignal()

    # This is called when the scanner is going into shutdown / power saving.
    scanner_shutdown = pyqtSignal()

    scanner_starting = pyqtSignal()
    scanner_running = pyqtSignal(float)
    scanner_receiving = pyqtSignal()
    scanner_success = pyqtSignal()
    scanner_jam = pyqtSignal()
    scanner_no_paper = pyqtSignal()

    def __init__(self, parent):
        super().__init__(parent)
        self.ctrl = ScannerControl()
        self.ctrl.state_change = self.state_change.emit
        self.ctrl.scanner_ready = self.scanner_ready.emit
        self.ctrl.scanner_shutdown = self.scanner_shutdown.emit
        self.ctrl.scanner_starting = self.scanner_starting.emit
        self.ctrl.scanner_running = self.scanner_running.emit
        self.ctrl.scanner_receiving = self.scanner_receiving.emit
        self.ctrl.scanner_success = self._scanner_success
        self.ctrl.scanner_jam = self.scanner_jam.emit
        self.ctrl.scanner_no_paper = self.scanner_no_paper.emit

    def _scanner_success(self, img: Image.Image):
        self._last_image = img
        self.scanner_success.emit()

    def get_last_image(self) -> Image.Image | None:
        res = self._last_image
        self._last_image = None
        return res

    def startup(self):
        self.ctrl.startup()

    def can_scan(self) -> bool:
        """Ensures that the scanner is ready and can scan now."""
        return self.ctrl.can_scan()

    def shutdown(self):
        """Shuts down the scanner (asynchronously)."""
        return self.ctrl.shutdown()

    def reset(self):
        return self.ctrl.reset()

    def stop(self):
        self.ctrl.scan_stop()

    def scan(self, long: bool):
        return self.ctrl.scan(long)
