import json
from PyQt5.QtCore import pyqtSignal, QThread
from scanapp.widgets.base import exc
import os
import datetime
import requests

from scanapp.env import API_TARGET, API_KEY
from scanapp.widgets.sendmail import Attachment


class ApiSender(QThread):
    done = pyqtSignal()
    failure = pyqtSignal(str, str)

    def __init__(self, parent, name: str, purpose: str, iban: str, attachments: list[Attachment]):
        super().__init__(parent)
        self.json_data = {
            "name": name,
            "purpose": purpose,
            "iban": iban,
        }
        self.attachments = attachments

    @exc
    def run(self):
        r = requests.post(
            API_TARGET,
            headers={"Api-Key": API_KEY},
            json=self.json_data,
            files={
                attachment.name: (attachment.name, attachment.data, f"{attachment.mime_main}/{attachment.mime_sub}")
                for attachment in self.attachments
            },
        )
        try:
            r.raise_for_status()
        except Exception as e:
            os.makedirs("failed_data", exist_ok=True)
            filename_base = f"failed_data/{datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}"
            with open(f"{filename_base}.json", 'w') as wf:
                json.dump(self.json_data, wf)
            for attachment in self.attachments:
                with open(f"{filename_base}.{attachment.name}", 'wb') as wbf:
                    wbf.write(attachment.data)
            self.failure.emit(str(e), filename_base)
