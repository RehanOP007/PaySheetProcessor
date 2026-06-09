import os
import smtplib
import sys
from email.message import EmailMessage


def load_env_file(path):
    if not os.path.exists(path):
        return

    with open(path, "r", encoding="utf-8") as env_file:
        for line in env_file:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue

            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")

            if key and key not in os.environ:
                os.environ[key] = value


def main():
    load_env_file(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

    smtp_host = os.environ.get("SMTP_HOST")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_username = os.environ.get("SMTP_USERNAME")
    smtp_password = os.environ.get("SMTP_PASSWORD")
    from_email = os.environ.get("FROM_EMAIL", smtp_username)
    smtp_use_tls = os.environ.get("SMTP_USE_TLS", "true").strip().lower() != "false"
    smtp_use_ssl = os.environ.get("SMTP_USE_SSL", "false").strip().lower() == "true"
    to_email = sys.argv[1] if len(sys.argv) > 1 else from_email

    missing = [
        name
        for name, value in [
            ("SMTP_HOST", smtp_host),
            ("SMTP_USERNAME", smtp_username),
            ("SMTP_PASSWORD", smtp_password),
            ("FROM_EMAIL", from_email),
        ]
        if not value
    ]
    if missing:
        raise RuntimeError(f"Missing .env value(s): {', '.join(missing)}")

    msg = EmailMessage()
    msg["Subject"] = "Payroll SMTP test"
    msg["From"] = from_email
    msg["To"] = to_email
    body = (
        "Hi NAME,\n\n"
        "Please find the attached salary slip for the month of May 2026.\n\n"
        "*Please make sure to keep this email confidential and you must not share/show this email "
        "with anyone regarding salary. Please note that if we become aware that this has been done, "
        "we will have to take action in accordance with the company's disciplinary policies.\n\n"
        "Thank you.\n"
        "HR Department.\n\n"
        "Please do not reply."
    )
    msg.set_content(body)

    print("Email template preview:")
    print(body)
    print()

    print(f"Connecting to {smtp_host}:{smtp_port}")
    print(f"Logging in as {smtp_username}")
    print(f"Sending test email to {to_email}")

    smtp_client = smtplib.SMTP_SSL if smtp_use_ssl else smtplib.SMTP

    with smtp_client(smtp_host, smtp_port, timeout=30) as server:
        server.set_debuglevel(1)
        if smtp_use_tls and not smtp_use_ssl:
            server.starttls()
        server.login(smtp_username, smtp_password)
        server.send_message(msg)

    print("Email sent successfully.")


if __name__ == "__main__":
    main()
