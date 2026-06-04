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
    msg.set_content("SMTP test email sent from PaySheetProcessor.")

    print(f"Connecting to {smtp_host}:{smtp_port}")
    print(f"Logging in as {smtp_username}")
    print(f"Sending test email to {to_email}")

    with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as server:
        server.set_debuglevel(1)
        server.starttls()
        server.login(smtp_username, smtp_password)
        server.send_message(msg)

    print("Email sent successfully.")


if __name__ == "__main__":
    main()
