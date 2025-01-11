from PyQt5.QtCore import QTimer
from PyQt5.QtGui import QPixmap, QGuiApplication
from PyQt5.QtWidgets import QLabel, QLineEdit, QPushButton, QVBoxLayout, QHBoxLayout, QStackedLayout, QWidget, QDialogButtonBox, QProgressBar

from scanapp.widgets.sendapi import ApiSender
import schwifty

from scanapp.widgets.base import exc
from scanapp.widgets.message_dialog import MessageDialog
from scanapp.widgets.scanner_controller import ScannerController
from scanapp.scanner_control import ScannerState
from scanapp.stitcher import ScanCollector
from scanapp.widgets.sendmail import MailSender, Attachment
from scanapp.env import SEND_TARGET



class ScanWidget(QWidget):
    INSTRUCTION_TEXT_BEGIN = "Bitte sicherstellen, dass Scanner leer ist, dann auf 'Ok' klicken."
    INSTRUCTION_TEXT_JAM = "Bitte sicherstellen, dass Scanner leer ist, dann auf 'Ok' klicken.\nBei langen Rechnungen, die Rechnung in mehreren Teilen scannen, maximal A4."
    INSTRUCTION_TEXT_EMPTY = "Rechnung einlegen, dann auf 'Ok' klicken."
    INSTRUCTION_BUTTON_TEXT_START = "Scanner startet. Nichts einlegen!"
    INSTRUCTION_BUTTON_TEXT_INSERT = "Rechnung einlegen, dann klicken."
    INSTRUCTION_BUTTON_TEXT_SCANNING = "Scannen..."
    INSTRUCTION_BUTTON_TEXT_SENDING = "Sende E-Mail..."
    SCANNING_STARTING = "Scanner startet..."
    SCANNING_SCANNING = "Scannen..."
    SCANNING_RECEIVING = "Empfange Daten..."
    SENDING_MAIL_TEXT = "Sende Scan als Mail an Rechnungen..."
    FORMRESET_TIMEOUT = 5*60
    PAGE_START = 0
    PAGE_SCAN = 1
    PAGE_INFO = 2
    PAGE_DONEMORE = 3

    PROCBAR_UPDATE_INTERVAL = 0.2

    SCAN_START_DURATION = 5
    SCANNING_DURATION = 12
    RECEIVING_DURATION = 10

    scan_collector: ScanCollector | None = None

    def __init__(self, parent):
        super().__init__(parent)

        self.scanner = ScannerController(self)
        self.scanner.state_change.connect(self._dbg_state_update)
        self.scanner.scanner_ready.connect(self._scanner_ready)
        self.scanner.scanner_shutdown.connect(self._scanner_unready)
        self.scanner.scanner_success.connect(lambda data: self._scan_result_ready(data))
        self.scanner.scanner_starting.connect(lambda: self._show_status(self.SCANNING_STARTING, self.SCAN_START_DURATION))
        self.scanner.scanner_running.connect(lambda: self._show_status(self.SCANNING_SCANNING, self.SCANNING_DURATION))
        self.scanner.scanner_receiving.connect(lambda: self._show_status(self.SCANNING_RECEIVING, self.RECEIVING_DURATION))
        self.scanner.scanner_jam.connect(self._paper_jam)
        self.scanner.scanner_no_paper.connect(lambda: self._retry_startup(is_empty=True))

        # Create stacked layout and add layouts
        self.stacked_layout = QStackedLayout(self)
        self.stacked_layout.setStackingMode(QStackedLayout.StackingMode.StackOne)

        scan_button = QPushButton("Rechnung Scannen")
        self.stacked_layout.addWidget(scan_button)
        scan_button.clicked.connect(lambda *_: self._show_scanner())

        scan_page = QWidget(self)
        input_layout = QVBoxLayout()
        name_box = QHBoxLayout()
        self.name_input = QLineEdit(self)
        name_box.addWidget(QLabel("Name:"), stretch=0)
        name_box.addWidget(self.name_input, stretch=1)
        purpose_box = QHBoxLayout()
        self.purpose_input = QLineEdit(self)
        purpose_box.addWidget(QLabel("Zweck:"), stretch=0)
        purpose_box.addWidget(self.purpose_input, stretch=1)
        iban_box = QHBoxLayout()
        self.iban_input = QLineEdit(self)
        iban_box.addWidget(QLabel("IBAN:"), stretch=0)
        iban_box.addWidget(self.iban_input, stretch=1)
        self.scan_button = QPushButton(self.INSTRUCTION_BUTTON_TEXT_START)
        self.scan_button.clicked.connect(self._initiate_scan)
        close_button = QPushButton("Schließen")
        close_button.clicked.connect(self.clear)
        self.dbg_scanner_state = QLabel("Scanner State: PowerDown")
        input_layout.addLayout(name_box)
        input_layout.addLayout(purpose_box)
        input_layout.addLayout(iban_box)
        input_layout.addWidget(self.scan_button)
        input_layout.addWidget(close_button)
        input_layout.addStretch()
        input_layout.addWidget(self.dbg_scanner_state, stretch=0)
        scan_page.setLayout(input_layout)
        self.stacked_layout.addWidget(scan_page)

        progress = QWidget(self)
        progress_layout = QVBoxLayout()
        progress_layout.addStretch()
        self.processing_label = QLabel("")
        progress_layout.addWidget(self.processing_label)
        self.processing_progbar = QProgressBar(self)
        progress_layout.addWidget(self.processing_progbar)
        progress_layout.addStretch()
        self.processing_procupdate = QTimer(self)
        self.processing_procupdate.setSingleShot(False)
        self.processing_procupdate.setInterval(int(self.PROCBAR_UPDATE_INTERVAL * 1000))
        self.processing_procupdate.timeout.connect(self._update_procbar)
        progress.setLayout(progress_layout)
        self.stacked_layout.addWidget(progress)

        done_more = QWidget(self)
        done_more_layout = QVBoxLayout()
        done_more_layout.addStretch()
        self.scan_preview = QLabel()
        done_more_layout.addWidget(self.scan_preview, stretch=1)
        self.scan_more_button = QPushButton("Weiter Scannen")
        self.scan_more_button.clicked.connect(self._scan_more)
        done_more_layout.addWidget(self.scan_more_button)
        add_button = QPushButton("Weitere Rechnung Scannen")
        add_button.clicked.connect(self._scan_next)
        done_more_layout.addWidget(add_button)
        done_button = QPushButton("Mail Senden")
        done_button.clicked.connect(self._send_mail)
        done_more_layout.addWidget(done_button)
        done_more.setLayout(done_more_layout)
        self.stacked_layout.addWidget(done_more)

        # Set up timer for auto reset
        self.reset_timer = QTimer(self)
        self.reset_timer.setSingleShot(True)
        self.reset_timer.timeout.connect(self.clear)

        self.stacked_layout.setCurrentIndex(self.PAGE_START)

    @exc
    def _retry_startup(self, is_jam: bool = False, is_empty: bool = False):
        self.reset_timer.stop()
        self.reset_timer.start()
        self.stacked_layout.setCurrentIndex(self.PAGE_SCAN)
        if is_empty:
            title = "Scanner Leer"
            msg = self.INSTRUCTION_TEXT_EMPTY
        elif is_jam:
            title = "Paper Jam"
            msg = self.INSTRUCTION_TEXT_JAM
        else:
            title = "Hinweis"
            msg = self.INSTRUCTION_TEXT_BEGIN
        dlg = MessageDialog(self, title, msg, QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Abort)
        def accept(*_):
            dlg.close()
            if is_empty:
                self._initiate_scan()
            elif is_jam:
                self.scanner.reset()
                self._show_scanner()
            else:
                self._show_scanner()
        dlg.buttons.accepted.connect(accept)
        dlg.buttons.rejected.connect(lambda *_: dlg.close() and self.clear())
        dlg.exec()
    
    @exc
    def _paper_jam(self):
        self._retry_startup(is_jam=True)

    @exc
    def clear(self, *_):
        self.name_input.clear()
        self.purpose_input.clear()
        self.iban_input.clear()
        self.scan_button.setEnabled(False)
        self.scan_button.setText(self.INSTRUCTION_BUTTON_TEXT_START)
        self.stacked_layout.setCurrentIndex(self.PAGE_START)
        self.scanner.shutdown()
        self.reset_timer.stop()
        self.scan_collector = None

    def _reset_reset_timer(self):
        self.reset_timer.stop()
        self.reset_timer.start(int(self.FORMRESET_TIMEOUT * 1000))

    @exc
    def _scanner_ready(self, *_):
        self.scan_button.setEnabled(True)
        self.scan_button.setText(self.INSTRUCTION_BUTTON_TEXT_INSERT)

    @exc
    def _scanner_unready(self, *_):
        self.scan_button.setEnabled(False)
        self.scan_button.setText(self.INSTRUCTION_BUTTON_TEXT_START)

    @exc
    def _dbg_state_update(self, state: ScannerState):
        self.dbg_scanner_state.setText(f"Scanner State: {state.name}")

    @exc
    def _show_scanner(self, *_):
        self.stacked_layout.setCurrentIndex(self.PAGE_DONEMORE)
        self.scan_collector = ScanCollector((self.scan_preview.width(), self.scan_preview.height()))
        self.stacked_layout.setCurrentIndex(self.PAGE_SCAN)
        self.name_input.setFocus()
        QGuiApplication.inputMethod().show()
        self.scan_button.setEnabled(False)
        self._reset_reset_timer()
        self.scanner.startup()
    
    def _input_failure(self, msg: str):
        dlg = MessageDialog(self, "Falsche Eingabe", msg, QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Abort)
        dlg.buttons.accepted.connect(lambda *_: dlg.close() and self._show_scanner())
        dlg.buttons.rejected.connect(lambda *_: dlg.close() and self.clear())
        dlg.exec()

    @exc
    def _initiate_scan(self, *_):
        if len(self.name_input.text()) < 2:
            self._input_failure("Bitte Namen eingeben")
            return
        if len(self.purpose_input.text()) < 2:
            self._input_failure("Bitte Zweck eingeben")
            return
        try:
            schwifty.IBAN(self.iban_input.text())
        except schwifty.exceptions.SchwiftyException as e:
            #self._input_failure(f"IBAN ungültig: {e}")
            # return
            pass
        if not self.scanner.can_scan():
            self._retry_startup()
        else:
            self.scan_button.setEnabled(False)
            self._show_status(self.SCANNING_STARTING, self.SCAN_START_DURATION)
            self.scanner.scan()

    @exc
    def _update_procbar(self, *_):
        self.processing_progbar.setValue(self.processing_progbar.value() + 1)
        if self.processing_progbar.value() == self.processing_progbar.maximum():
            self.processing_procupdate.stop()

    @exc
    def _show_status(self, status_message: str, duration: float | None):
        self.processing_label.setText(status_message)
        self.stacked_layout.setCurrentIndex(self.PAGE_INFO)
        if duration is None:
            self.processing_procupdate.stop()
            self.processing_progbar.setVisible(False)
        else:
            self.processing_progbar.setVisible(True)
            self.processing_progbar.setValue(0)
            self.processing_progbar.setRange(0, int(duration/self.PROCBAR_UPDATE_INTERVAL))
            self.processing_procupdate.start()
    
    @exc
    def _scan_result_ready(self, data: bytes):
        with open("last.png", "wb") as wf:
            wf.write(data)
        self.scan_collector.append(data)
        self._show_donemore()

    @exc
    def _send_mail(self, *_):
        images = self.scan_collector.get_all()
        self._show_status(self.SENDING_MAIL_TEXT, None)
        if SEND_TARGET == "mail":
            sender_cls = MailSender
        elif SEND_TARGET == "api":
            sender_cls = ApiSender
        sender = sender_cls(
            self,
            name=self.name_input.text(),
            purpose=self.purpose_input.text(),
            iban=self.iban_input.text(),
            attachments=[
                Attachment(name=f"scan_{idx}.jpg", mime_main="image", mime_sub="jpeg", data=img)
                for idx, img in enumerate(images)
            ],
        )
        sender.done.connect(self._show_scanner)
        sender.failure.connect(self._mail_failure)
        sender.start()

    @exc
    def _mail_failure(self, msg: str, saved_path: str):
        dlg = MessageDialog(self, "Mail Failure", f"Email konnte nicht versendet werden: {msg}\nBitte administrator kontaktieren.\nMail wurde lokal gespeichert unter:\n{saved_path}", QDialogButtonBox.StandardButton.Ok)
        dlg.buttons.accepted.connect(lambda *_: dlg.close() and self._show_scanner())
        dlg.exec()

    @exc
    def _scan_more(self, *_):
        # Just scan another
        self._initiate_scan()

    @exc
    def _scan_next(self, *_):
        # Bake the last image
        self.scan_collector.begin_next()
        self._initiate_scan()

    @exc
    def _show_donemore(self):
        self.scan_more_button.setEnabled(self.scan_collector.can_continue())
        self.stacked_layout.setCurrentIndex(self.PAGE_DONEMORE)
        self.scan_preview.setPixmap(QPixmap.fromImage(self.scan_collector.qthumbnail()))
