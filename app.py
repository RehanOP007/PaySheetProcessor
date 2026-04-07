from flask import Flask, render_template, request, send_file, redirect, url_for, flash
import pandas as pd
import os
import pdfkit
from datetime import datetime
import webbrowser
import sys
import shutil
from waitress import serve

app = Flask(__name__)
app.secret_key = "secret123"

# --- PATH LOGIC FOR EXE ---
if getattr(sys, 'frozen', False):
    base_dir = os.path.dirname(sys.executable)
else:
    base_dir = os.path.dirname(os.path.abspath(__file__))

UPLOAD_FOLDER = os.path.join(base_dir, "uploads")
OUTPUT_FOLDER = os.path.join(base_dir, "output")
LOGO_FOLDER = os.path.join(base_dir, "logos")

os.makedirs(LOGO_FOLDER, exist_ok=True)
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# GLOBAL DATAFRAME
global_df = None

# WKHTMLTOPDF CONFIG (CROSS PLATFORM)
if sys.platform == "win32":
    wkhtml_path = r"C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe"
else:
    wkhtml_path = shutil.which("wkhtmltopdf") or "/usr/local/bin/wkhtmltopdf"

if not os.path.exists(wkhtml_path):
    raise FileNotFoundError(f"❌ wkhtmltopdf not found at {wkhtml_path}")

print(f"✅ Using wkhtmltopdf: {wkhtml_path}")

config = pdfkit.configuration(wkhtmltopdf=wkhtml_path)

# PDF OPTIONS
pdf_options = {
    "enable-local-file-access": None,
    "encoding": "UTF-8"
}


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
        # Load Excel
        df = pd.read_excel(path, header=1)

        # Clean columns
        df = df.loc[:, ~df.columns.astype(str).str.contains("^Unnamed", na=False)]
        df.columns = (
            df.columns.astype(str)
            .str.strip()
            .str.lower()
            .str.replace(r'[\s/&]+', '_', regex=True)
        )

        # Remove invalid rows
        if "emp_number" not in df.columns:
            flash("Column 'emp_number' not found in uploaded file", "error")
            return redirect(url_for("index"))

        df = df.dropna(subset=["emp_number"])

        global_df = df
        print(f"✅ Processed columns: {df.columns.tolist()}")

        flash("Excel file uploaded successfully!", "success")
        return redirect(url_for("index"))

    except Exception as e:

        error_msg = f"Error reading Excel file: {str(e)}"
        flash(error_msg, "error")
        return redirect(url_for("index"))


@app.route("/generate", methods=["POST"])
def generate():
    global global_df

    if global_df is None:
        flash("Please upload an Excel file first!", "error")
        return redirect(url_for("index"))

    company = request.form.get("company", "venturecorp")
    pay_period = request.form.get("pay_period")
    action = request.form.get("action")
    emp_id = request.form.get("emp_id")

    if not pay_period:
        flash("Please select a pay period.", "error")
        return redirect(url_for("index"))

    try:
        date_obj = datetime.strptime(pay_period, "%Y-%m")
        month_str = date_obj.strftime("%B")
        year_str = date_obj.strftime("%Y")

        # Filter data
        if action == "one" and emp_id:
            data = global_df[global_df["emp_number"].astype(str) == str(emp_id)]
            if data.empty:
                return f"Employee ID {emp_id} not found!"
            output_name = f"{company}_{emp_id}_{pay_period}.pdf"
        else:
            data = global_df
            output_name = f"{company}_All_Payslips_{pay_period}.pdf"

        pdf_path = os.path.join(OUTPUT_FOLDER, output_name)

        # Logo
        logo_file = f"{company.lower()}.png"
        logo_path = os.path.abspath(os.path.join(LOGO_FOLDER, logo_file))
        if not os.path.exists(logo_path):
            logo_path = None

        template_file = f"{company.lower()}.html"

        html = render_template(
            template_file,
            employees=data.to_dict(orient="records"),
            month=month_str,
            year=year_str,
            logo_path=logo_path
        )

        pdfkit.from_string(
            html,
            pdf_path,
            configuration=config,
            options=pdf_options
        )

        return send_file(pdf_path, as_attachment=True)

    except Exception as e:
        return f"Error: {str(e)}. Make sure template exists in templates folder."


@app.route("/generate-one", methods=["POST"])
def generate_one():
    global global_df

    if global_df is None:
        return "Upload Excel first!"

    try:
        emp_id = request.form.get("emp_id")
        company = request.form.get("company", "venturecorp")
        pay_period = request.form.get("pay_period", datetime.now().strftime("%Y-%m"))

        date_obj = datetime.strptime(pay_period, "%Y-%m")
        month_str = date_obj.strftime("%B")
        year_str = date_obj.strftime("%Y")

        emp_data = global_df[global_df["emp_number"].astype(str) == str(emp_id)]

        if emp_data.empty:
            return f"Employee {emp_id} not found!"

        pdf_name = f"{emp_id}_payslip.pdf"
        pdf_path = os.path.join(OUTPUT_FOLDER, pdf_name)
        template_file = f"{company.lower()}.html"

        logo_file = f"{company.lower()}.png"
        logo_path = os.path.abspath(os.path.join(LOGO_FOLDER, logo_file))
        if not os.path.exists(logo_path):
            logo_path = None

        html = render_template(
            template_file,
            employees=emp_data.to_dict(orient="records"),
            month=month_str,
            year=year_str,
            logo_path=logo_path
        )

        pdfkit.from_string(
            html,
            pdf_path,
            configuration=config,
            options=pdf_options
        )

        return send_file(pdf_path, as_attachment=True)

    except Exception as e:
        return f"Error generating single payslip: {str(e)}"


if __name__ == "__main__":
    host = "0.0.0.0"
    port = 5000
    url = f"http://127.0.0.1:{port}"

    print(f"🚀 Server running on {host}:{port}")
    print(f"🌐 Open in browser: {url}")
    print("Close this window to stop.")

    # Open browser only on local Windows/macOS/Linux run, not inside Docker
    if os.environ.get("WERKZEUG_RUN_MAIN") != "true" and not os.environ.get("DOCKER_CONTAINER"):
        try:
            webbrowser.open(url)
        except Exception:
            pass

    serve(app, host=host, port=port, threads=6)