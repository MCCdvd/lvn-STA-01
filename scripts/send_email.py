from __future__ import annotations

import argparse
import os
import smtplib
import ssl
import time
from email.message import EmailMessage

SMTP_HOST = 'smtp.gmail.com'
SMTP_PORT = 587


def _read_text(body: str | None, body_file: str | None) -> str:
    if body_file:
        with open(body_file, 'r', encoding='utf-8') as handle:
            return handle.read()
    return body or ''


def send_email(subject: str, body: str, recipient: str, retries: int, retry_delay: int) -> None:
    sender = os.environ.get('EMAIL_ADDRESS')
    password = os.environ.get('EMAIL_PASSWORD')

    if not sender or not password:
        raise RuntimeError('EMAIL_ADDRESS and EMAIL_PASSWORD environment variables are required')

    msg = EmailMessage()
    msg['Subject'] = subject
    msg['From'] = sender
    msg['To'] = recipient
    msg.set_content(body)

    context = ssl.create_default_context()
    last_error: Exception | None = None

    for attempt in range(1, retries + 1):
        try:
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=60) as server:
                server.ehlo()
                server.starttls(context=context)
                server.ehlo()
                server.login(sender, password)
                server.send_message(msg)
            return
        except (smtplib.SMTPException, TimeoutError, OSError) as exc:
            last_error = exc
            if attempt == retries:
                break
            time.sleep(retry_delay)

    raise RuntimeError(f'Failed to send email after {retries} attempts: {last_error}')


def main() -> None:
    parser = argparse.ArgumentParser(description='Send notification email through Gmail SMTP')
    parser.add_argument('--to', required=True, help='Recipient email address')
    parser.add_argument('--subject', required=True)
    parser.add_argument('--body', default=None)
    parser.add_argument('--body-file', default=None)
    parser.add_argument('--retries', type=int, default=3)
    parser.add_argument('--retry-delay', type=int, default=10)
    args = parser.parse_args()

    body = _read_text(args.body, args.body_file)
    send_email(
        subject=args.subject,
        body=body,
        recipient=args.to,
        retries=max(1, args.retries),
        retry_delay=max(1, args.retry_delay),
    )
    print(f'Email sent to {args.to}')


if __name__ == '__main__':
    main()
