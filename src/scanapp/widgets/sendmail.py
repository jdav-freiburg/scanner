import datetime
import os
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage

from PyQt5.QtCore import QThread, pyqtSignal

from scanapp.env import (
    MAIL_FROM,
    MAIL_HOST,
    MAIL_PASSWORD,
    MAIL_PORT,
    MAIL_SSL,
    MAIL_START_TLS,
    MAIL_TO,
    MAIL_USER,
)
from scanapp.widgets.base import exc


@dataclass
class Attachment:
    name: str
    mime_main: str
    mime_sub: str
    data: bytes


class MailSender(QThread):
    done = pyqtSignal()
    failure = pyqtSignal(str, str)

    def __init__(self, parent, name: str, purpose: str, iban: str, attachments: list[Attachment]):
        super().__init__(parent)
        self.subject = f"Neue Rechnung von {name}"
        self.text = (
            f"{name} hat eine Rechnung einreicht:\n"
            f"  Name: {name}\n"
            f"  Zweck: {purpose}\n"
            f"  IBAN: {iban}\n"
        )
        self.attachments = attachments

    @exc
    def run(self):
        # Create a text/plain message
        msg = EmailMessage()
        msg.set_content(self.text.encode(), maintype="text", subtype="text")

        # me == the sender's email address
        # you == the recipient's email address
        msg["Subject"] = self.subject
        msg["From"] = MAIL_FROM
        msg["To"] = MAIL_TO
        for attachment in self.attachments:
            msg.add_attachment(
                attachment.data,
                maintype=attachment.mime_main,
                subtype=attachment.mime_sub,
                filename=attachment.name,
            )

        # Send the message via our own SMTP server.
        try:
            if MAIL_SSL:
                s = smtplib.SMTP_SSL(MAIL_HOST, MAIL_PORT)
            else:
                s = smtplib.SMTP(MAIL_HOST, MAIL_PORT)
            if MAIL_START_TLS:
                s.starttls()
            if MAIL_USER and MAIL_PASSWORD:
                s.login(MAIL_USER, MAIL_PASSWORD)
            s.send_message(msg)
            s.quit()
            print("Successfully sent mail")
        except Exception as e:
            print(f"Failed to send mail: {e!r}")
            os.makedirs("failed_mails", exist_ok=True)
            filename = f"failed_mails/{datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.eml"
            print(f"Saving to {filename}")
            with open(filename, "wb") as wf:
                wf.write(msg.as_bytes())
            self.failure.emit(str(e), filename)
        self.done.emit()
