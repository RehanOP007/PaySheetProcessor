from flask import Flask, render_template, request, send_file, redirect, url_for, flash, jsonify
import pandas as pd
import os
import math
import pdfkit
from datetime import datetime, date
import calendar
from pypdf import PdfWriter, PdfReader
import webbrowser
import sys
import shutil
import re
import smtplib
import zipfile
from email.message import EmailMessage
from waitress import serve

app = Flask(__name__)
app.secret_key = "newfjypkjrypornu"

# --- PATH LOGIC FOR EXE ---
if getattr(sys, 'frozen', False):
    base_dir = os.path.dirname(sys.executable)
else:
    base_dir = os.path.dirname(os.path.abspath(__file__))


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


load_env_file(os.path.join(base_dir, ".env"))

UPLOAD_FOLDER = os.path.join(base_dir, "uploads")
OUTPUT_FOLDER = os.path.join(base_dir, "output")
LOGO_FOLDER   = os.path.join(base_dir, "logos")

os.makedirs(LOGO_FOLDER,   exist_ok=True)
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# ── GLOBAL DATAFRAME ─────────────────────────────────────────────────────────
global_df = None

# ── WKHTMLTOPDF CONFIG ───────────────────────────────────────────────────────
if sys.platform == "win32":
    wkhtml_path = r"C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe"
else:
    wkhtml_path = shutil.which("wkhtmltopdf") or "/usr/local/bin/wkhtmltopdf"

if not os.path.exists(wkhtml_path):
    raise FileNotFoundError(f"❌ wkhtmltopdf not found at {wkhtml_path}")

print(f"✅ Using wkhtmltopdf: {wkhtml_path}")
config = pdfkit.configuration(wkhtmltopdf=wkhtml_path)

pdf_options = {
    "enable-local-file-access": None,
    "encoding": "UTF-8",
    "page-size": "A5",
    "margin-top": "5mm",
    "margin-bottom": "5mm",
    "margin-left": "5mm",
    "margin-right": "5mm",
    "zoom": "0.9",
    "print-media-type": None
}

# ── CUSTOM JINJA2 FILTERS ────────────────────────────────────────────────────

def _to_float(val):
    """Convert any value to float; NaN / None / bad strings → 0.0"""
    try:
        f = float(val)
        return 0.0 if (math.isnan(f) or math.isinf(f)) else f
    except (TypeError, ValueError):
        return 0.0

def safe_fmt(val):
    """Format as comma-separated 2-dp string. NaN/None → '0.00'"""
    return "{:,.2f}".format(_to_float(val))

def safe_numval(val):
    """Return numeric float for comparisons/arithmetic in templates."""
    return _to_float(val)

def safe_fmtf(val):
    """Format a float already computed in the template."""
    try:
        return "{:,.2f}".format(float(val))
    except (TypeError, ValueError):
        return "0.00"

def fmt_payment_date(val):
    """Convert 'YYYY-MM-DD' or date object to d/m/YYYY with no leading zeros."""
    if not val:
        return ""
    try:
        if isinstance(val, str):
            d = datetime.strptime(val, "%Y-%m-%d")
        else:
            d = val
        return f"{d.day}/{d.month}/{d.year}"
    except (ValueError, TypeError):
        return str(val)

app.jinja_env.filters["fmt"]     = safe_fmt
app.jinja_env.filters["numval"]  = safe_numval
app.jinja_env.filters["fmtf"]    = safe_fmtf
app.jinja_env.filters["datefmt"] = fmt_payment_date

# ── HELPER: is this emp_number an intern? ────────────────────────────────────

def is_intern(emp_number):
    return str(emp_number).strip().upper().endswith("INT")

# ── HELPER: last day of a month as d/m/yyyy string ───────────────────────────

def last_day_of_month(year: int, month: int) -> str:
    last = calendar.monthrange(year, month)[1]
    return f"{last}/{month}/{year}"


def safe_filename(value):
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value).strip())
    return cleaned.strip("_") or "employee"


def employee_email_column(df):
    candidates = [
        "email",
        "email_address",
        "work_email",
        "company_email",
        "official_email",
        "employee_email",
    ]
    for column in candidates:
        if column in df.columns:
            return column
    return None


def get_payroll_context(company, pay_period, payment_date):
    date_obj = datetime.strptime(pay_period, "%Y-%m")
    month_str = date_obj.strftime("%B")
    year_str = date_obj.strftime("%Y")

    logo_file = f"{company.lower()}.png"
    logo_path = os.path.abspath(os.path.join(LOGO_FOLDER, logo_file))
    if not os.path.exists(logo_path):
        logo_path = None

    return date_obj, month_str, year_str, logo_path


def employee_template_and_name(company, emp_id, pay_period):
    if is_intern(emp_id):
        return "innobotINT.html", f"{safe_filename(emp_id)}_{pay_period}_intern.pdf"
    return f"{company.lower()}.html", f"{safe_filename(emp_id)}_{pay_period}_payslip.pdf"

# ── HELPER: render + save one PDF, return path ───────────────────────────────

def render_pdf(template_file, employees, month_str, year_str, logo_path,
               pay_period, payment_date, date_obj, output_name):
    """Render a Jinja2 template to PDF and return the output path."""
    pdf_path = os.path.join(OUTPUT_FOLDER, output_name)

    html = render_template(
        template_file,
        employees=employees,
        month=month_str,
        year=year_str,
        logo_path=logo_path,
        payment_date=payment_date,
    )

    pdfkit.from_string(html, pdf_path, configuration=config, options=pdf_options)
    return pdf_path


def render_employee_pdf(emp_id, company, pay_period, payment_date):
    data = global_df[global_df["emp_number"].astype(str) == str(emp_id)]
    if data.empty:
        raise ValueError(f"Employee ID {emp_id} not found")

    date_obj, month_str, year_str, logo_path = get_payroll_context(company, pay_period, payment_date)
    template_file, output_name = employee_template_and_name(company, emp_id, pay_period)

    return render_pdf(
        template_file,
        data.to_dict(orient="records"),
        month_str,
        year_str,
        logo_path,
        pay_period,
        payment_date,
        date_obj,
        output_name
    )


def render_combined_pdf(company, pay_period, payment_date):
    date_obj, month_str, year_str, logo_path = get_payroll_context(company, pay_period, payment_date)

    mask_intern = (
        global_df["emp_number"]
        .astype(str)
        .str.upper()
        .str.startswith("IB")
        &
        global_df["emp_number"]
        .astype(str)
        .str.upper()
        .str.endswith("INT")
    )
    df_regulars = global_df[~mask_intern]
    df_interns = global_df[mask_intern]

    generated = []

    if not df_regulars.empty:
        generated.append(render_pdf(
            f"{company.lower()}.html",
            df_regulars.to_dict(orient="records"),
            month_str,
            year_str,
            logo_path,
            pay_period,
            payment_date,
            date_obj,
            f"_tmp_{company}_regulars_{pay_period}.pdf"
        ))

    if not df_interns.empty:
        generated.append(render_pdf(
            "innobotINT.html",
            df_interns.to_dict(orient="records"),
            month_str,
            year_str,
            logo_path,
            pay_period,
            payment_date,
            date_obj,
            f"_tmp_{company}_interns_{pay_period}.pdf"
        ))

    if len(generated) == 1:
        return generated[0]

    merged_path = os.path.join(OUTPUT_FOLDER, f"{company}_All_Payslips_{pay_period}.pdf")
    writer = PdfWriter()
    for tmp_path in generated:
        reader = PdfReader(tmp_path)
        for page in reader.pages:
            writer.add_page(page)

    with open(merged_path, "wb") as f:
        writer.write(f)

    for tmp_path in generated:
        try:
            os.remove(tmp_path)
        except Exception:
            pass

    return merged_path


def send_employee_email(to_email, employee_name, pdf_path, company, pay_period):
    smtp_host = os.environ.get("SMTP_HOST")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_username = os.environ.get("SMTP_USERNAME")
    smtp_password = os.environ.get("SMTP_PASSWORD")
    from_email = os.environ.get("FROM_EMAIL", smtp_username)
    smtp_use_tls = os.environ.get("SMTP_USE_TLS", "true").strip().lower() != "false"
    smtp_use_ssl = os.environ.get("SMTP_USE_SSL", "false").strip().lower() == "true"

    if not all([smtp_host, smtp_username, smtp_password, from_email]):
        raise RuntimeError("Email is not configured. Set SMTP_HOST, SMTP_PORT, SMTP_USERNAME, SMTP_PASSWORD and FROM_EMAIL.")

    msg = EmailMessage()
    msg["Subject"] = f"{company} payslip - {pay_period}"
    msg["From"] = from_email
    msg["To"] = to_email
    msg.set_content(
        f"Dear {employee_name},\n\n"
        f"Please find attached your payslip for {pay_period}.\n\n"
        "Regards,\nPayroll Team"
    )

    with open(pdf_path, "rb") as f:
        msg.add_attachment(
            f.read(),
            maintype="application",
            subtype="pdf",
            filename=os.path.basename(pdf_path)
        )

    smtp_client = smtplib.SMTP_SSL if smtp_use_ssl else smtplib.SMTP

    with smtp_client(smtp_host, smtp_port, timeout=30) as server:
        if smtp_use_tls and not smtp_use_ssl:
            server.starttls()
        server.login(smtp_username, smtp_password)
        server.send_message(msg)


# ── ROUTES ───────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/upload", methods=["POST"])
def upload():
    global global_df

    if "file" not in request.files:
        flash("No file part")
        return redirect(url_for("index"))

    file = request.files["file"]
    if file.filename == "":
        flash("No file selected")
        return redirect(url_for("index"))

    path = os.path.join(UPLOAD_FOLDER, file.filename)
    file.save(path)

    try:
        df = pd.read_excel(path, header=1)

        df = df.loc[:, ~df.columns.astype(str).str.contains("^Unnamed", na=False)]
        df.columns = (
            df.columns.astype(str)
            .str.strip()
            .str.lower()
            .str.replace(r'[\s/&]+', '_', regex=True)
        )

        if "emp_number" not in df.columns:
            flash("Column 'emp_number' not found in uploaded file", "error")
            return redirect(url_for("index"))

        df = df.dropna(subset=["emp_number"])

        # Drop stray purely-numeric column names (e.g. '315')
        df = df.loc[:, ~df.columns.str.match(r'^\d+$')]

        global_df = df
        print(f"✅ Processed columns: {df.columns.tolist()}")

        # Summary counts
        intern_count  = df["emp_number"].astype(str).str.upper().str.endswith("INT").sum()
        regular_count = len(df) - intern_count
        flash(f"Excel uploaded: {regular_count} employee(s), {intern_count} intern(s).", "success")
        return redirect(url_for("index"))

    except Exception as e:
        flash(f"Error reading Excel file: {str(e)}", "error")
        return redirect(url_for("index"))


@app.route("/generate", methods=["POST"])
def generate():
    global global_df

    if global_df is None:
        flash("Please upload an Excel file first!", "error")
        return redirect(url_for("index"))

    company      = request.form.get("company", "venturecorp")
    pay_period   = request.form.get("pay_period")
    payment_date = request.form.get("payment_date")
    action       = request.form.get("action")
    emp_id       = request.form.get("emp_id")

    if not pay_period:
        flash("Please select a pay period.", "error")
        return redirect(url_for("index"))

    try:
        # ── Single employee ──────────────────────────────────────────────────
        if action == "one" and emp_id:
            pdf_path = render_employee_pdf(emp_id, company, pay_period, payment_date)
            return send_file(pdf_path, as_attachment=True)

        # ── All employees — split interns vs regulars, merge into one PDF ────
        else:
            pdf_path = render_combined_pdf(company, pay_period, payment_date)
            return send_file(pdf_path, as_attachment=True,
                             download_name=f"{company}_All_Payslips_{pay_period}.pdf")

    except Exception as e:
        return f"Error: {str(e)}. Make sure template exists in templates folder."


@app.route("/finalise", methods=["POST"])
def finalise():
    global global_df

    if global_df is None:
        flash("Please upload an Excel file first!", "error")
        return redirect(url_for("index"))

    company = request.form.get("company", "venturecorp")
    pay_period = request.form.get("pay_period")
    payment_date = request.form.get("payment_date")

    if not pay_period or not payment_date:
        flash("Please select pay period and payment date.", "error")
        return redirect(url_for("index"))

    email_col = employee_email_column(global_df)
    employees = []
    for _, row in global_df.iterrows():
        emp_id = str(row.get("emp_number", "")).strip()
        employees.append({
            "emp_number": emp_id,
            "name": str(row.get("name", "")).strip(),
            "email": "" if email_col is None or pd.isna(row.get(email_col)) else str(row.get(email_col)).strip(),
            "kind": "Intern" if is_intern(emp_id) else "Employee",
        })

    return render_template(
        "finalise.html",
        employees=employees,
        company=company,
        pay_period=pay_period,
        payment_date=payment_date,
        email_column=email_col,
    )


@app.route("/download-employee/<emp_id>")
def download_employee(emp_id):
    if global_df is None:
        flash("Please upload an Excel file first!", "error")
        return redirect(url_for("index"))

    company = request.args.get("company", "venturecorp")
    pay_period = request.args.get("pay_period")
    payment_date = request.args.get("payment_date")

    try:
        pdf_path = render_employee_pdf(emp_id, company, pay_period, payment_date)
        return send_file(pdf_path, as_attachment=True)
    except Exception as e:
        return f"Error generating payslip: {str(e)}"


@app.route("/download-all", methods=["POST"])
def download_all_finalised():
    if global_df is None:
        flash("Please upload an Excel file first!", "error")
        return redirect(url_for("index"))

    company = request.form.get("company", "venturecorp")
    pay_period = request.form.get("pay_period")
    payment_date = request.form.get("payment_date")

    try:
        pdf_path = render_combined_pdf(company, pay_period, payment_date)
        return send_file(pdf_path, as_attachment=True,
                         download_name=f"{company}_All_Payslips_{pay_period}.pdf")
    except Exception as e:
        return f"Error generating all payslips: {str(e)}"


@app.route("/download-zip", methods=["POST"])
def download_zip():
    if global_df is None:
        flash("Please upload an Excel file first!", "error")
        return redirect(url_for("index"))

    company = request.form.get("company", "venturecorp")
    pay_period = request.form.get("pay_period")
    payment_date = request.form.get("payment_date")
    zip_name = f"{company}_Separate_Payslips_{pay_period}.zip"
    zip_path = os.path.join(OUTPUT_FOLDER, zip_name)

    try:
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
            for _, row in global_df.iterrows():
                emp_id = str(row.get("emp_number", "")).strip()
                pdf_path = render_employee_pdf(emp_id, company, pay_period, payment_date)
                archive.write(pdf_path, arcname=os.path.basename(pdf_path))

        return send_file(zip_path, as_attachment=True, download_name=zip_name)
    except Exception as e:
        return f"Error creating ZIP: {str(e)}"


@app.route("/send-emails", methods=["POST"])
def send_emails():
    if global_df is None:
        flash("Please upload an Excel file first!", "error")
        return redirect(url_for("index"))

    company = request.form.get("company", "venturecorp")
    pay_period = request.form.get("pay_period")
    payment_date = request.form.get("payment_date")
    email_col = employee_email_column(global_df)

    if email_col is None:
        flash("No email column found. Use a column like email, email_address, work_email or company_email.", "error")
        return redirect(url_for("index"))

    sent = 0
    skipped = 0
    errors = []

    for _, row in global_df.iterrows():
        emp_id = str(row.get("emp_number", "")).strip()
        employee_name = str(row.get("name", emp_id)).strip() or emp_id
        to_email = row.get(email_col)

        if pd.isna(to_email) or not str(to_email).strip():
            skipped += 1
            continue

        try:
            pdf_path = render_employee_pdf(emp_id, company, pay_period, payment_date)
            send_employee_email(str(to_email).strip(), employee_name, pdf_path, company, pay_period)
            sent += 1
        except Exception as e:
            errors.append(f"{emp_id}: {str(e)}")

    if errors:
        flash(f"Sent {sent} email(s), skipped {skipped}. Errors: {'; '.join(errors[:3])}", "error")
    else:
        flash(f"Sent {sent} email(s). Skipped {skipped} employee(s) without email.", "success")

    return redirect(url_for("index"))


@app.route("/send-email-one", methods=["POST"])
def send_email_one():
    if global_df is None:
        return jsonify({"ok": False, "message": "Please upload an Excel file first."}), 400

    payload = request.get_json(silent=True) or request.form
    company = payload.get("company", "venturecorp")
    pay_period = payload.get("pay_period")
    payment_date = payload.get("payment_date")
    emp_id = str(payload.get("emp_id", "")).strip()
    email_col = employee_email_column(global_df)

    if email_col is None:
        return jsonify({"ok": False, "message": "No email column found."}), 400

    data = global_df[global_df["emp_number"].astype(str) == emp_id]
    if data.empty:
        return jsonify({"ok": False, "message": f"Employee {emp_id} not found."}), 404

    row = data.iloc[0]
    employee_name = str(row.get("name", emp_id)).strip() or emp_id
    to_email = row.get(email_col)

    if pd.isna(to_email) or not str(to_email).strip():
        return jsonify({
            "ok": True,
            "status": "skipped",
            "emp_id": emp_id,
            "message": f"{employee_name} skipped: missing email.",
        })

    try:
        pdf_path = render_employee_pdf(emp_id, company, pay_period, payment_date)
        send_employee_email(str(to_email).strip(), employee_name, pdf_path, company, pay_period)
        return jsonify({
            "ok": True,
            "status": "sent",
            "emp_id": emp_id,
            "message": f"Sent to {employee_name} ({to_email}).",
        })
    except Exception as e:
        return jsonify({
            "ok": False,
            "status": "error",
            "emp_id": emp_id,
            "message": f"{emp_id}: {str(e)}",
        }), 500


@app.route("/generate-one", methods=["POST"])
def generate_one():
    global global_df

    if global_df is None:
        return "Upload Excel first!"

    try:
        emp_id       = request.form.get("emp_id")
        company      = request.form.get("company", "venturecorp")
        pay_period   = request.form.get("pay_period", datetime.now().strftime("%Y-%m"))
        payment_date = request.form.get("payment_date")

        date_obj  = datetime.strptime(pay_period, "%Y-%m")
        month_str = date_obj.strftime("%B")
        year_str  = date_obj.strftime("%Y")

        emp_data = global_df[global_df["emp_number"].astype(str) == str(emp_id)]
        if emp_data.empty:
            return f"Employee {emp_id} not found!"

        logo_file = f"{company.lower()}.png"
        logo_path = os.path.abspath(os.path.join(LOGO_FOLDER, logo_file))
        if not os.path.exists(logo_path):
            logo_path = None

        if is_intern(emp_id):
            template_file = "innobotINT.html"
            pdf_name      = f"{emp_id}_intern_allowance.pdf"
        else:
            template_file = f"{company.lower()}.html"
            pdf_name      = f"{emp_id}_payslip.pdf"

        pdf_path = render_pdf(
            template_file,
            emp_data.to_dict(orient="records"),
            month_str, year_str, logo_path,
            pay_period, payment_date, date_obj, pdf_name
        )
        return send_file(pdf_path, as_attachment=True)

    except Exception as e:
        return f"Error generating payslip: {str(e)}"


@app.route("/clear", methods=["POST"])
def clear():
    global global_df
    global_df = None
    flash("Uploaded file cleared. You can upload a new file.", "success")
    return redirect(url_for("index"))


# ── MAIN ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    host = "0.0.0.0"
    port = 5000
    url  = f"http://127.0.0.1:{port}"

    print(f"🚀 Server running on {host}:{port}")
    print(f"🌐 Open in browser: {url}")
    print("Close this window to stop.")

    if os.environ.get("WERKZEUG_RUN_MAIN") != "true" and not os.environ.get("DOCKER_CONTAINER"):
        try:
            webbrowser.open(url)
        except Exception:
            pass

    serve(app, host=host, port=port, threads=6)
