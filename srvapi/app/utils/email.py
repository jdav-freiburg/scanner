from aiosmtplib import SMTP
from app.models.request import BillPayload


async def send_email(payload: BillPayload, filenames: list[str]):
    """
    Send an email with the bill details.
    """
    email_content = f"""
    Name: {payload.name}
    Purpose: {payload.purpose}
    IBAN: {payload.iban}
    Files: {', '.join(filenames)}
    """
    # Example email sending (Replace with real SMTP details)
    message = f"Subject: New Bill Uploaded\n\n{email_content}"
    try:
        smtp = SMTP(hostname="smtp.example.com", port=587, use_tls=True)
        await smtp.connect()
        await smtp.login("your_email@example.com", "your_password")
        await smtp.sendmail(
            from_addr="your_email@example.com",
            to_addrs=["recipient@example.com"],
            message=message
        )
    except Exception as e:
        print(f"Error sending email: {e}")
