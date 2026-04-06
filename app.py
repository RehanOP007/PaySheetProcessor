from flask import Flask, render_template, request, send_file, redirect, url_for, flash
import pandas as pd
import os
import pdfkit
from datetime import datetime
import webbrowser
import sys
from waitress import serve

app = Flask(__name__)
app.secret_key = "secret123" 

# --- PATH LOGIC FOR EXE ---
# Determine if we are running as a bundled EXE or a normal script
if getattr(sys, 'frozen', False):
    # If EXE, use the directory of the EXE file
    base_dir = os.path.dirname(sys.executable)
else:
    # If script, use the directory of the script
    base_dir = os.path.dirname(os.path.abspath(__file__))

# Apply the base_dir to your folders so they sit next to the EXE
UPLOAD_FOLDER = os.path.join(base_dir, "uploads")
OUTPUT_FOLDER = os.path.join(base_dir, "output")
LOGO_FOLDER = os.path.join(base_dir, "logos")

# Ensure folders exist
os.makedirs(LOGO_FOLDER, exist_ok=True)
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

global_df = None

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/upload", methods=["POST"])
def upload():
    global global_df
    if 'file' not in request.files:
        flash("No file part")
        return redirect(url_for('index'))
    
    file = request.files["file"]
    if file.filename == '':
        return redirect(url_for('index'))

    path = os.path.join(UPLOAD_FOLDER, file.filename)
    file.save(path)

    # Load Excel - header=1 skips the very first row (Base Package/EXTRAS)
    df = pd.read_excel(path, header=1)
    
    # Normalize column names: strip spaces, lowercase, replace spaces with underscores
    df = df.loc[:, ~df.columns.str.contains('^Unnamed')]
    df.columns = df.columns.str.strip().str.lower().str.replace(r'[\s/]+', '_', regex=True)

    # Remove rows where Employee Number is missing
    df = df.dropna(subset=['emp_number'])
    
    global_df = df
    print(f"Successfully processed columns: {df.columns.tolist()}")
    flash("Excel file uploaded successfully!")
    return redirect(url_for('index'))

@app.route("/generate", methods=["POST"])
def generate():
    global global_df
    if global_df is None:
        flash("Please upload an Excel file first!")
        return redirect(url_for("index"))

    company = request.form.get("company", "venturecorp")
    pay_period = request.form.get("pay_period") # Expected format from HTML: YYYY-MM
    action = request.form.get("action")
    emp_id = request.form.get("emp_id")

    if not pay_period:
        return "Please select a pay period."

    # Parse Month and Year for the display
    date_obj = datetime.strptime(pay_period, '%Y-%m')
    month_str = date_obj.strftime('%B')
    year_str = date_obj.strftime('%Y')

    # Data Filtering
    if action == "one" and emp_id:
        data = global_df[global_df['emp_number'].astype(str) == str(emp_id)]
        if data.empty:
            return f"Employee ID {emp_id} not found in the uploaded file!"
        output_name = f"{company}_{emp_id}_{pay_period}.pdf"
    else:
        data = global_df
        output_name = f"{company}_All_Payslips_{pay_period}.pdf"

    pdf_path = os.path.join(OUTPUT_FOLDER, output_name)
    
    # Logo Logic
    logo_file = f"{company.lower()}.png"
    logo_path = os.path.abspath(os.path.join(LOGO_FOLDER, logo_file))
    if not os.path.exists(logo_path):
        logo_path = None

    # Render HTML
    # Note: 'template_file' maps to venturecorp.html, consultant.html, or intern.html
    template_file = f"{company.lower()}.html"
    
    try:
        html = render_template(
            template_file,
            employees=data.to_dict(orient="records"),
            month=month_str,
            year=year_str,
            logo_path=logo_path
        )

        options = {
            "enable-local-file-access": None,
            "encoding": "UTF-8"
        }

        config = pdfkit.configuration(wkhtmltopdf=r"C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe")
        
        pdfkit.from_string(html, pdf_path, configuration=config, options=options)
        return send_file(pdf_path, as_attachment=True)
    
    except Exception as e:
        return f"Error: {str(e)}. Make sure {template_file} exists in the templates folder."

# 🔍 Individual Generation helper
@app.route("/generate-one", methods=["POST"])
def generate_one():
    global global_df
    if global_df is None:
        return "Upload Excel first!"

    emp_id = request.form.get("emp_id")
    company = request.form.get("company", "venturecorp")
    pay_period = request.form.get("pay_period", datetime.now().strftime('%Y-%m'))

    # Normalize dates
    date_obj = datetime.strptime(pay_period, '%Y-%m')
    month_str = date_obj.strftime('%B')
    year_str = date_obj.strftime('%Y')

    emp_data = global_df[global_df["emp_number"].astype(str) == str(emp_id)]

    if emp_data.empty:
        return f"Employee {emp_id} not found!"

    pdf_name = f"{emp_id}_payslip.pdf"
    pdf_path = os.path.join(OUTPUT_FOLDER, pdf_name)
    template_file = f"{company.lower()}.html"

    html = render_template(
        template_file,
        employees=emp_data.to_dict(orient="records"),
        month=month_str,
        year=year_str
    )

    config = pdfkit.configuration(wkhtmltopdf=r"C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe")
    pdfkit.from_string(html, pdf_path, configuration=config, options={"enable-local-file-access": None})

    return send_file(pdf_path, as_attachment=True)

if __name__ == "__main__":
    # 1. Define the URL
    url = "http://127.0.0.1:5000"
    
    # 2. Print status to CMD
    print(f"Starting production server on {url}")
    print("Close this window to stop the program.")
    
    # 3. Open the browser FIRST
    # We use a slight delay logic or just call it before the blocking serve call
    webbrowser.open(url)
    
    # 4. Start the blocking production server
    serve(app, host='127.0.0.1', port=5000, threads=6)