# main.py
# This Python script is designed to be deployed as a serverless function
# (e.g., on Google Cloud Functions). It creates a web server that listens for
# file uploads, processes them, and returns a structured JSON report.

# Required libraries:
# Flask==2.3.2
# google-generativeai==0.5.4
# PyPDF2==3.0.1
# python-docx==1.1.0
# flask-cors==4.0.0

import os
import io
import json
import time
import PyPDF2
import docx
import google.generativeai as genai
import google.api_core.exceptions
from docx.shared import Inches
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS


# --- Gemini API Configuration ---
# IMPORTANT: Replace "" with your actual Gemini API key.
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY") 
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)


# --- Flask App Initialization ---
app = Flask(__name__)

# This CORS setup allows the frontend to communicate with this backend server.
CORS(app, resources={r"/*": {"origins": [
    "https://feasibility-1.onrender.com", 
    "http://127.0.0.1:5001"
]}})


# --- Helper Functions for File Parsing ---

def extract_text_from_pdf(file_stream):
    """Reads a PDF file stream and returns its text content."""
    try:
        pdf_reader = PyPDF2.PdfReader(file_stream)
        text = ""
        for page in pdf_reader.pages:
            text += page.extract_text() or ""
        return text
    except Exception as e:
        print(f"Error reading PDF: {e}")
        return None

def extract_text_from_docx(file_stream):
    """Reads a DOCX file stream and returns its text content."""
    try:
        document = docx.Document(file_stream)
        text = "\n".join([para.text for para in document.paragraphs])
        return text
    except Exception as e:
        print(f"Error reading DOCX: {e}")
        return None

# --- Main API Endpoints ---

@app.route('/')
def index():
    """A simple route to confirm the server is running."""
    return "The backend server is running. Please use the frontend to upload files."

# In main.py

@app.route('/generate-report', methods=['POST'])
def generate_report_handler():
    """
    Handles the main report generation request.
    """
    print("Received request to /generate-report")

    # This part remains the same, as file handling is correct.
    if 'templateFile' not in request.files or 'sourceFile' not in request.files:
        return jsonify({"error": "Missing template or source file"}), 400

    template_file = request.files['templateFile']
    source_file = request.files['sourceFile']

    try:
        template_stream = io.BytesIO(template_file.read())
        source_stream = io.BytesIO(source_file.read())

        if template_file.filename.endswith('.docx'):
            template_text = extract_text_from_docx(template_stream)
        else:
            template_text = template_stream.read().decode('utf-8', errors='ignore')

        if source_file.filename.endswith('.pdf'):
            source_text = extract_text_from_pdf(source_stream)
        elif source_file.filename.endswith('.docx'):
            source_text = extract_text_from_docx(source_stream)
        else:
            source_text = source_stream.read().decode('utf-8', errors='ignore')

        if not source_text: # We only truly need the source text now
            return jsonify({"error": "Could not extract text from the source file."}), 500

    except Exception as e:
        print(f"An error occurred during file processing: {e}")
        return jsonify({"error": "Failed to process files"}), 500

    try:
        if not GEMINI_API_KEY:
             return jsonify({"error": "Gemini API key is not configured on the server."}), 500

        ### CHANGE 1: UPGRADED AI MODEL ###
        # Using a more powerful model for better accuracy on complex documents.
        model = genai.GenerativeModel("gemini-2.5-pro")

        ### CHANGE 2: NEW, MORE FLEXIBLE PROMPT ###
        # This prompt analyzes the source document directly, ignoring the template.
        # This makes it a universal document parser.
        prompt = f"""
        You are an expert data extraction assistant. Your task is to analyze the SOURCE DOCUMENT and convert its contents into a structured JSON object.

        **SOURCE DOCUMENT:**
        ---
        {source_text}
        ---

        **INSTRUCTIONS:**
        1.  Analyze the source document to identify the main header information and the primary data table.
        2.  Return the result as a single, raw JSON object with two keys: "header" and "table". Do not wrap the JSON in markdown backticks.
        3.  The "header" key should contain an object of key-value pairs based on the information at the top of the source document (e.g., Customer name, Part Number, Date).
        4.  The "table" key should contain an object with "columns" (a list of strings representing the table headers) and "rows" (a list of lists representing the data in each row).
        5.  If any table cells appear to be for user input (like empty measurement boxes), represent them as empty strings in the JSON.
        """

        # This part for the API call and retry logic remains the same.
        max_retries = 3
        retry_delay = 15 # seconds
        for attempt in range(max_retries):
            try:
                response = model.generate_content(prompt)
                cleaned_text = response.text.strip().replace("```json", "").replace("```", "")
                result_json = json.loads(cleaned_text)
                return jsonify(result_json) # Success, exit the loop and function
            except google.api_core.exceptions.ResourceExhausted as e:
                print(f"Rate limit exceeded. Retrying in {retry_delay} seconds... (Attempt {attempt + 1}/{max_retries})")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                else:
                    raise e # Re-raise the exception on the last attempt
            except Exception as e:
                # This will catch JSON parsing errors if the AI returns a bad response
                print(f"Error processing AI response on attempt {attempt + 1}: {e}")
                if attempt >= max_retries - 1:
                    raise e # Re-raise the exception on the last attempt
                time.sleep(retry_delay)


    except Exception as e:
        print(f"An error occurred during AI processing: {e}")
        if isinstance(e, google.api_core.exceptions.ResourceExhausted):
            return jsonify({"error": "API rate limit exceeded. Please wait a minute and try again."}), 429
        # This will now catch errors from both the API call and JSON parsing
        return jsonify({"error": "Failed to generate report from AI model. The document structure might be too complex or invalid."}), 500
    
@app.route('/export-docx', methods=['POST'])
def export_docx_handler():
    """
    Receives report data in JSON format and returns a DOCX file.
    """
    print("Received request to /export-docx")
    
    if not request.is_json:
        return jsonify({"error": "Request must be JSON"}), 400
        
    data = request.get_json()
    
    try:
        document = docx.Document()
        document.add_heading('Inspection Report', level=1)

        for key, value in data.get('header', {}).items():
            document.add_paragraph(f"{key}: {value}", style='BodyText')

        document.add_paragraph() 

        table_data = data.get('table', {})
        columns = table_data.get('columns', [])
        rows = table_data.get('rows', [])

        if columns and rows:
            table = document.add_table(rows=1, cols=len(columns))
            table.style = 'Table Grid'
            
            hdr_cells = table.rows[0].cells
            for i, col_name in enumerate(columns):
                hdr_cells[i].text = col_name

            for row_data in rows:
                row_cells = table.add_row().cells
                for i, cell_text in enumerate(row_data):
                    row_cells[i].text = str(cell_text)
        
        file_stream = io.BytesIO()
        document.save(file_stream)
        file_stream.seek(0)

        return send_file(
            file_stream,
            as_attachment=True,
            download_name='inspection_report.docx',
            mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        )

    except Exception as e:
        print(f"Error creating DOCX file: {e}")
        return jsonify({"error": "Failed to create DOCX file"}), 500


if __name__ == '__main__':
    app.run(debug=True, port=5001, host='0.0.0.0')
