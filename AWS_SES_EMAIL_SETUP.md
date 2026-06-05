# AWS SES SMTP Email Setup

Update `.env` in this project folder with your AWS SES SMTP values:

```env
SMTP_HOST=email-smtp.us-east-1.amazonaws.com
SMTP_PORT=587
SMTP_USE_TLS=true
SMTP_USE_SSL=false
SMTP_USERNAME=YOUR_SES_SMTP_USERNAME
SMTP_PASSWORD=YOUR_SES_SMTP_PASSWORD
FROM_EMAIL=payroll@example.com
```

Change `us-east-1` to the AWS region where SES is configured.

Important:

- `SMTP_USERNAME` and `SMTP_PASSWORD` must be generated from the AWS SES SMTP credentials page. Do not use your normal AWS access key and secret.
- `FROM_EMAIL` must be verified in SES.
- If your SES account is still in sandbox mode, every recipient email address must also be verified.

Test email sending with:

```powershell
python test_email.py recipient@example.com
```

If your network closes the connection after sending the email data, try SES SMTP over SSL instead:

```env
SMTP_PORT=465
SMTP_USE_TLS=false
SMTP_USE_SSL=true
```
