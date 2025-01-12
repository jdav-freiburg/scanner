from email.message import EmailMessage
import os
from dataclasses import dataclass
from aiosmtplib import SMTP
from app.models.bill import BillPayload

MAIL_TO = os.environ.get("MAIL_TO", "postmaster@localhost")
MAIL_FROM = os.environ.get("MAIL_FROM", "postmaster@localhost")
MAIL_SSL = bool(os.environ.get("MAIL_SSL", ""))
MAIL_START_TLS = bool(os.environ.get("MAIL_START_TLS", ""))
MAIL_HOST = os.environ.get("MAIL_HOST", "localhost")
MAIL_PORT = os.environ.get("MAIL_PORT", 587 if MAIL_SSL or MAIL_START_TLS else 25)
MAIL_USER = os.environ.get("MAIL_USER")
MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD")


@dataclass
class Attachment:
    name: str
    mime_main: str
    mime_sub: str
    data: bytes


async def send_email(payload: BillPayload, attachments: list[Attachment]) -> bool:
    """
    Send an email with the bill details.
    """
    # Create a text/plain message
    msg = EmailMessage()
    msg.set_content((
        f"{payload.name} hat eine Rechnung einreicht:\n"
        f"  Name: {payload.name}\n"
        f"  Zweck: {payload.purpose}\n"
        f"  IBAN: {payload.iban}\n"
    ).encode(), maintype="text", subtype="text")

    # me == the sender's email address
    # you == the recipient's email address
    msg['Subject'] = f"Neue Rechnung von {payload.name}"
    msg['From'] = MAIL_FROM
    msg['To'] = MAIL_TO
    for attachment in attachments:
        msg.add_attachment(
            attachment.data,
            maintype=attachment.mime_main,
            subtype=attachment.mime_sub,
            filename=attachment.name,
        )

    try:
        smtp = SMTP(hostname=MAIL_HOST, port=MAIL_PORT, use_tls=MAIL_SSL, start_tls=MAIL_START_TLS)
        await smtp.connect()
        if MAIL_USER and MAIL_PASSWORD:
            await smtp.login(MAIL_USER, MAIL_PASSWORD)
        await smtp.send_message(message=msg)
        await smtp.quit()
    except Exception as e:
        print(f"Error sending email: {e}")
        return False
    return True
