"""Sending the invitation email.

With SMTP configured the mail goes out for real. Without it - local development,
and any deployment where mail has not been set up yet - the message is written to
the server log instead, so the flow still works end to end and the link is
recoverable. It is deliberately *not* returned through the API: the whole point
of the invitation is that only the recipient learns the token.
"""

import os
import smtplib
import sys
from email.message import EmailMessage


def smtp_configured():
    return bool(os.environ.get('SMTP_HOST'))


def app_base_url():
    return os.environ.get('APP_BASE_URL', 'http://localhost:5173').rstrip('/')


def invitation_link(token):
    return f'{app_base_url()}/set-password?token={token}'


def build_invitation(to_email, username, link, expires_in_days):
    message = EmailMessage()
    message['Subject'] = 'Ihr Zugang zum Schichtplan'
    message['From'] = os.environ.get('MAIL_FROM', 'schichtplan@example.com')
    message['To'] = to_email
    message.set_content(
        f'Hallo,\n\n'
        f'für Sie wurde ein Zugang zum Schichtplan angelegt.\n'
        f'Benutzername: {username}\n\n'
        f'Bitte vergeben Sie hier Ihr eigenes Passwort:\n{link}\n\n'
        f'Der Link ist {expires_in_days} Tage gültig und kann nur einmal verwendet werden.\n'
        f'Wenn Sie diesen Zugang nicht erwartet haben, können Sie diese E-Mail ignorieren.\n'
    )
    return message


def send_invitation(to_email, username, token, expires_in_days):
    """Returns True if the mail was handed to an SMTP server, False if logged."""
    link = invitation_link(token)
    message = build_invitation(to_email, username, link, expires_in_days)

    if not smtp_configured():
        # Printed rather than returned to the caller, so the token stays out of
        # the API response even in development.
        print(
            f'\n--- Einladung (kein SMTP konfiguriert, daher nicht versendet) ---\n'
            f'An:    {to_email}\n'
            f'Konto: {username}\n'
            f'Link:  {link}\n'
            f'----------------------------------------------------------------\n',
            file=sys.stderr, flush=True,
        )
        return False

    host = os.environ['SMTP_HOST']
    port = int(os.environ.get('SMTP_PORT', '587'))
    user = os.environ.get('SMTP_USER')
    password = os.environ.get('SMTP_PASSWORD')
    use_tls = os.environ.get('SMTP_USE_TLS', 'true').lower() != 'false'

    with smtplib.SMTP(host, port, timeout=15) as smtp:
        if use_tls:
            smtp.starttls()
        if user and password:
            smtp.login(user, password)
        smtp.send_message(message)
    return True
