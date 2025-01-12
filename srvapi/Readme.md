## The backend for the server-side email api

This provides a ready docker container providing an api for sending mails coming from the scanner.

## Usage

### Environment variables

- `MAIL_TO`: The target email-address to receive all emails. Required.
- `MAIL_FROM`: The source email address to send mails from. Required.
- `MAIL_SSL`: If not empty, use ssl.
- `MAIL_START_TLS`: If not empty, use starttls.
- `MAIL_HOST`: The target smtp host. Required.
- `MAIL_PORT`: The target smtp port (defaults to 25/587).
- `MAIL_USER`: If not empty, use this user to login.
- `MAIL_PASSWORD`: If not empty, use this password to login.

### docker-compose

```
services:
  scanner-srvapi:
    image: ghcr.io/jdav-freiburg/scanner-srvapi:2025-01-12
    restart: unless-stopped

    environment:
      MAIL_HOST: "mailhost"
      MAIL_FROM: "account@example.com"
      MAIL_TO: "account@example.com"
```
