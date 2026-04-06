from flask import Flask, render_template, request, send_file, redirect, url_for
import pandas as pd
import os
import pdfkit
from datetime import datetime
from flask import flash

app = Flask(__name__)
app.secret_key = "secret123" 

UPLOAD_FOLDER = "uploads"
OUTPUT_FOLDER = "output"
LOGO_FOLDER = "logos"
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
        return redirect(url_for('index'))
    
    file = request.files["file"]
    path = os.path.join(UPLOAD_FOLDER, file.filename)
    file.save(path)

    # Use header=1 to skip the Base Package/EXTRAS row 
    df = pd.read_excel(path, header=1)
    
    # Remove Unnamed columns and normalize names to lower_snake_case
    df = df.loc[:, ~df.columns.str.contains('^Unnamed')]
    df.columns = df.columns.str.strip().str.lower().str.replace(r'[\s/]+', '_', regex=True)

    # Clean empty rows 
    df = df.dropna(subset=['emp_number'])
    
    global_df = df
    print(f"Normalized columns: {df.columns.tolist()}")
    return redirect(url_for('index'))

@app.route("/generate", methods=["POST"])
def generate():
    global global_df
    if global_df is None:
        flash("Please upload an Excel file first!")
        return redirect(url_for("index"))

    company = request.form.get("company")
    pay_period = request.form.get("pay_period") # Format: YYYY-MM
    action = request.form.get("action")
    emp_id = request.form.get("emp_id")

    # Parse Month and Year
    date_obj = datetime.strptime(pay_period, '%Y-%m')
    month_str = date_obj.strftime('%B')
    year_str = date_obj.strftime('%Y')

    # Select template based on company selection
    template_file = f"{company.lower()}.html"

    # Filter data based on single vs all
    if action == "one" and emp_id:
        data = global_df[global_df['emp_number'].astype(str) == str(emp_id)]
        if data.empty:
            return f"Employee {emp_id} not found!"
        output_name = f"{company}_{emp_id}_{pay_period}.pdf"
    else:
        data = global_df
        output_name = f"{company}_All_Payslips_{pay_period}.pdf"

    pdf_path = os.path.join(OUTPUT_FOLDER, output_name)
    
    logo_file = f"{company.lower()}.png"   # or .jpg depending on your files
    logo_path = os.path.abspath(os.path.join(LOGO_FOLDER, logo_file))

    # Optional safety check
    if not os.path.exists(logo_path):
        logo_path = None

    html = render_template(
        template_file,
        employees=data.to_dict(orient="records"),
        month=month_str,
        year=year_str,
        logo_path=logo_path
    )

    options = {
    "enable-local-file-access": None
    }

    config = pdfkit.configuration(wkhtmltopdf=r"C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe")
    pdfkit.from_string(
        html,
        pdf_path,
        configuration=config,
        options=options
    )

    return send_file(pdf_path, as_attachment=True)


# 🔍 Generate ONE payslip by employee number
@app.route("/generate-one", methods=["POST"])
def generate_one():
    global global_df

    emp_id = request.form.get("emp_id")

    if global_df is None:
        return "Upload Excel first!"

    df = global_df

    # Make sure column exists
    if "emp_number" not in df.columns:
        return "Column 'Emp Number' not found!"

    emp = df[df["emp_number"].astype(str) == str(emp_id)]

    if emp.empty:
        return "Employee not found!"

    pdf_path = os.path.join(OUTPUT_FOLDER, f"{emp_id}_payslip.pdf")

    html = render_template(
        "payslip.html",
        employees=emp.to_dict(orient="records")
    )

    pdfkit.from_string(html, pdf_path, configuration=pdfkit.configuration(
        wkhtmltopdf=r"C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe"
    ))

    return send_file(pdf_path, as_attachment=True)



if __name__ == "__main__":
    app.run(debug=True)
