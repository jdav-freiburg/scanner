import os

# SCREEN_RESOLUTION_WIDTH = int(os.environ.get("SCREEN_RESOLUTION_WIDTH", "480"))
# SCREEN_RESOLUTION_HEIGHT = int(os.environ.get("SCREEN_RESOLUTION_HEIGHT", "320"))
SCREEN_RESOLUTION_WIDTH = int(os.environ.get("SCREEN_RESOLUTION_WIDTH", "960"))
SCREEN_RESOLUTION_HEIGHT = int(os.environ.get("SCREEN_RESOLUTION_HEIGHT", "640"))

# "mail" or "api"
SEND_TARGET = os.environ.get("SEND_TARGET", "mail")

# Send the scanned result via api (SEND_TARGET=api)
API_TARGET = os.environ.get("API_TARGET", "http://localhost:8080/api/bill")
API_KEY = os.environ.get("API_KEY", "123456")

# Send the scanned result via mail (SEND_TARGET=mail)
MAIL_TO = os.environ.get("MAIL_TO", "postmaster@localhost")
MAIL_FROM = os.environ.get("MAIL_FROM", "postmaster@localhost")
MAIL_SSL = bool(os.environ.get("MAIL_SSL", ""))
MAIL_START_TLS = bool(os.environ.get("MAIL_START_TLS", ""))
MAIL_HOST = os.environ.get("MAIL_HOST", "localhost")
MAIL_PORT = int(os.environ.get("MAIL_PORT", 587 if MAIL_SSL or MAIL_START_TLS else 25))
MAIL_USER = os.environ.get("MAIL_USER")
MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD")
DISABLE_IBAN_CHECK = bool(os.environ.get("DISABLE_IBAN_CHECK", ""))
EMULATE_SCANNER = bool(os.environ.get("EMULATE_SCANNER", ""))
