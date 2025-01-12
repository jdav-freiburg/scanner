from PyQt5.QtCore import pyqtSignal, QObject
from scanapp.scanner_control import ScannerState, ScannerControl


class ScannerController(QObject):
    _state: ScannerState = ScannerState.PowerDown

    # Called whenever the state changes
    state_change = pyqtSignal(ScannerState)

    # This is called after ensure_startup(), when the scanner is ready to accept paper.
    scanner_ready = pyqtSignal()

    # This is called when the scanner is going into shutdown / power saving.
    scanner_shutdown = pyqtSignal()

    scanner_starting = pyqtSignal()
    scanner_running = pyqtSignal()
    scanner_receiving = pyqtSignal()
    scanner_success = pyqtSignal(bytes)
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
        self.ctrl.scanner_success = self.scanner_success.emit
        self.ctrl.scanner_jam = self.scanner_jam.emit
        self.ctrl.scanner_no_paper = self.scanner_no_paper.emit

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

    def scan(self):
        return self.ctrl.scan()