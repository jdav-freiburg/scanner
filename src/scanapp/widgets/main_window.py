from pathlib import Path

from PyQt5.QtCore import QTimer
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QMainWindow, QStackedLayout
from PyQt5.QtWidgets import QWidget

from scanapp.env import SCREEN_RESOLUTION_HEIGHT, SCREEN_RESOLUTION_WIDTH
from scanapp.widgets.base import exc
from scanapp.widgets.message_dialog import MessageDialog
from scanapp.widgets.scan import ScanWidget


STYLESHEET = (Path(__file__).parent / 'style.qss').read_text()
MessageDialog.MAIN_STYLE = STYLESHEET


class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()

        # Set window properties
        self.setWindowTitle("Control")
        self.showFullScreen()  # Set the window to fullscreen mode
        #self.setGeometry(0, 0, 320, 240)
        self.setFixedSize(SCREEN_RESOLUTION_WIDTH, SCREEN_RESOLUTION_HEIGHT)
        self.setCursor(Qt.BlankCursor)

        # Create central widget and set layout
        self.setCentralWidget(ScanWidget(self))
        self.setStyleSheet(STYLESHEET)
