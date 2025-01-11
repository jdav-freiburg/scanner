import os
# Set this before qt imports
os.environ["QT_IM_MODULE"] = "qtvirtualkeyboard"

import sys

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt, QObject
from PyQt5.QtGui import QGuiApplication, QRegion

from scanapp.widgets.main_window import MainWindow



def handleVisibleChanged():
    if not QGuiApplication.inputMethod().isVisible():
        return
    for w in QGuiApplication.allWindows():
        try:
            if w.metaObject().className() == "QtVirtualKeyboard::InputView":
                keyboard = w.findChild(QObject, "keyboard")
                if keyboard is not None:
                    r = w.geometry()
                    r.moveTop(int(keyboard.property("y")))
                    w.setMask(QRegion(r))
                    return
        except RuntimeError:
            pass


def main():
    # Create the application and show the pin input window
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_DisableHighDpiScaling, True)
    app = QApplication(sys.argv)
    QGuiApplication.inputMethod().visibleChanged.connect(handleVisibleChanged)
    main_window = MainWindow()
    main_window.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
