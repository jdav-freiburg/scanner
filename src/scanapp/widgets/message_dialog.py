from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QLabel, QVBoxLayout, QDialog, QDialogButtonBox, QSizePolicy

from scanapp.env import SCREEN_RESOLUTION_HEIGHT, SCREEN_RESOLUTION_WIDTH


class MessageDialog(QDialog):
    MAIN_STYLE: str

    def __init__(
        self,
        parent,
        title: str,
        message: str,
        buttons: QDialogButtonBox.StandardButton = QDialogButtonBox.StandardButton.Ok,
    ):
        super().__init__(parent, Qt.WindowType.FramelessWindowHint)
        self.setWindowTitle(title)

        title_label = QLabel(title, self)
        message_label = QLabel(message, self)

        if buttons != 0:
            self.buttons = QDialogButtonBox(buttons, Qt.Orientation.Horizontal, self)

            self.buttons.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
            )

        vbox = QVBoxLayout(self)
        vbox.addWidget(
            title_label,
            stretch=1,
            alignment=Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter,
        )
        vbox.addWidget(
            message_label,
            stretch=1,
            alignment=Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter,
        )
        if buttons != 0:
            vbox.addWidget(
                self.buttons,
                stretch=1,
                alignment=Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter,
            )

        self.showFullScreen()
        self.setFixedSize(SCREEN_RESOLUTION_WIDTH, SCREEN_RESOLUTION_HEIGHT)
        self.setGeometry(0, 0, SCREEN_RESOLUTION_WIDTH, SCREEN_RESOLUTION_HEIGHT)

        self.setStyleSheet(self.MAIN_STYLE)
