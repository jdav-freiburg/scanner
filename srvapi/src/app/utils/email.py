import os
from dataclasses import dataclass
from datetime import datetime
from email.message import EmailMessage
from io import BytesIO

from aiosmtplib import SMTP
from fpdf import FPDF
from PIL import Image

from app.models.bill import BillPayload

MAIL_TO = os.environ.get("MAIL_TO", "postmaster@localhost")
MAIL_FROM = os.environ.get("MAIL_FROM", "postmaster@localhost")
MAIL_SSL = bool(os.environ.get("MAIL_SSL", ""))
MAIL_START_TLS = bool(os.environ.get("MAIL_START_TLS", ""))
MAIL_HOST = os.environ.get("MAIL_HOST", "localhost")
MAIL_PORT = os.environ.get("MAIL_PORT", 587 if MAIL_SSL or MAIL_START_TLS else 25)
MAIL_USER = os.environ.get("MAIL_USER")
MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD")
CONVERT_TO_PDF = bool(os.environ.get("CONVERT_TO_PDF", "1"))


@dataclass
class Attachment:
    name: str
    mime_main: str
    mime_sub: str
    data: bytes


def to_pdf(payload: BillPayload, attachments: list[Attachment]) -> bytes:
    pdf = FPDF(unit="pt")
    pdf.add_page(format="A4")
    pdf.set_font("Arial", size=14)
    pdf.text(50, 65, f"Rechnung eingereicht von: {payload.name}")
    pdf.text(50, 95, f"Zweck: {payload.purpose}")
    pdf.text(50, 125, f"IBAN: {payload.iban}")

    for attachment in attachments:
        with BytesIO(attachment.data) as bio:
            with Image.open(bio) as img:
                width, height = img.size
            pdf.add_page(orientation="P", format=(width, height))
            bio.seek(0)
            pdf.image(bio, x=0, y=0, w=width, h=height)
    return pdf.output()


async def send_email(payload: BillPayload, attachments: list[Attachment]) -> bool:
    """
    Send an email with the bill details.
    """
    # Create a text/plain message
    msg = EmailMessage()
    msg.set_content(
        (
            f"{payload.name} hat eine Rechnung einreicht:<br>\n"
            f"  Name: {payload.name}<br>\n"
            f"  Zweck: {payload.purpose}<br>\n"
            f"  IBAN: {payload.iban}<br>\n"
        ).encode(),
        maintype="text",
        subtype="html",
    )

    # me == the sender's email address
    # you == the recipient's email address
    msg["Subject"] = f"Neue Rechnung von {payload.name}"
    msg["From"] = MAIL_FROM
    msg["To"] = MAIL_TO
    if CONVERT_TO_PDF:
        raw_pdf = to_pdf(payload, attachments)
        msg.add_attachment(
            raw_pdf,
            maintype="application",
            subtype="pdf",
            filename=f"scan-{datetime.now().strftime('%Y-%m-%d_%H:%M')}.pdf",
        )
        with open("dump.pdf", "wb") as wf:
            wf.write(raw_pdf)
    else:
        for attachment in attachments:
            msg.add_attachment(
                attachment.data,
                maintype=attachment.mime_main,
                subtype=attachment.mime_sub,
                filename=attachment.name,
            )

    try:
        smtp = SMTP(
            hostname=MAIL_HOST,
            port=MAIL_PORT,
            use_tls=MAIL_SSL,
            start_tls=MAIL_START_TLS,
        )
        await smtp.connect()
        if MAIL_USER and MAIL_PASSWORD:
            await smtp.login(MAIL_USER, MAIL_PASSWORD)
        await smtp.send_message(msg)
        await smtp.quit()
    except Exception as e:
        print(f"Error sending email: {e}")
        return False
    return True
