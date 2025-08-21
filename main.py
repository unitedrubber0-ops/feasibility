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

# Add this helper function above your generate_report_handler function.
# This avoids duplicating the retry logic.
def generate_with_retry(model, prompt, max_retries=3, retry_delay=5):
    """Calls the Gemini API with a given prompt and handles retries."""
    for attempt in range(max_retries):
        try:
            response = model.generate_content(prompt)
            # Clean the response text immediately
            cleaned_text = response.text.strip().replace("```json", "").replace("```", "")
            # Try to parse JSON to ensure it's valid before returning
            json.loads(cleaned_text)
            return cleaned_text  # Return the valid, cleaned JSON string
        except google.api_core.exceptions.ResourceExhausted as e:
            print(f"Rate limit exceeded. Retrying in {retry_delay}s... (Attempt {attempt + 1}/{max_retries})")
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
            else:
                raise e # Re-raise the exception on the last attempt
        except Exception as e:
            # This catches other errors, including JSON parsing failures
            print(f"Error on attempt {attempt + 1}: {e}. Retrying...")
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
            else:
                raise e # Re-raise on the final attempt


@app.route('/generate-report', methods=['POST'])
def generate_report_handler():
    """
    Handles the main report generation request using a two-step AI chain.
    """
    print("Received request to /generate-report")

    if 'templateFile' not in request.files or 'sourceFile' not in request.files:
        return jsonify({"error": "Missing template or source file"}), 400

    template_file = request.files['templateFile']
    source_file = request.files['sourceFile']

    try:
        # We need the text from both the template and the source file now
        template_stream = io.BytesIO(template_file.read())
        source_stream = io.BytesIO(source_file.read())

        if template_file.filename.endswith('.docx'):
            template_text = extract_text_from_docx(template_stream)
        else:
            template_text = template_stream.read().decode('utf-8', errors='ignore')

        if source_file.filename.endswith('.docx'):
            source_text = extract_text_from_docx(source_stream)
        elif source_file.filename.endswith('.pdf'):
            source_text = extract_text_from_pdf(source_stream)
        else:
            source_text = source_stream.read().decode('utf-8', errors='ignore')

        if not template_text or not source_text:
            return jsonify({"error": "Could not extract text from one or both files."}), 500

    except Exception as e:
        print(f"An error occurred during file processing: {e}")
        return jsonify({"error": "Failed to process files"}), 500

    try:
        if not GEMINI_API_KEY:
             return jsonify({"error": "Gemini API key is not configured on the server."}), 500

        model = genai.GenerativeModel("gemini-2.5-pro")

        # --- STEP 1: THE EXTRACTOR ---
        # First, extract structured data from the source document.
        prompt_extract = f"""
        You are an expert data extraction assistant. Your task is to analyze the SOURCE DOCUMENT and convert its contents into a structured JSON object.

        **SOURCE DOCUMENT:**
        ---
        {source_text}
        ---

        **INSTRUCTIONS:**
        1.  Analyze the source document to identify the main header information and the primary data table.
        2.  Return the result as a single, raw JSON object with two keys: "header" and "table".
        3.  The "header" key should contain key-value pairs from the top of the document.
        4.  The "table" key should contain "columns" (a list of headers) and "rows" (a list of lists).
        """
        
        print("Executing AI Step 1: Extracting data from source...")
        extracted_json_string = generate_with_retry(model, prompt_extract)
        extracted_json = json.loads(extracted_json_string)
        print("AI Step 1 successful. Extracted data.")


        # --- STEP 2: THE MAPPER ---
        # Now, map the extracted data into the template's structure.
        prompt_map = f"""
        You are a data mapping and transformation expert. You will be given a BLANK TEMPLATE and a JSON OBJECT containing source data. Your task is to create a new JSON object that follows the structure of the BLANK TEMPLATE, populated with data from the source JSON.

        **BLANK TEMPLATE:**
        ---
        {template_text}
        ---

        **SOURCE DATA JSON:**
        ---
        {json.dumps(extracted_json, indent=2)}
        ---

        **INSTRUCTIONS:**
        1.  Create a final JSON output with "header" and "table" keys, matching the structure of the BLANK TEMPLATE.
        2.  Populate the "header" of the final JSON using the corresponding values from the "header" of the SOURCE DATA JSON.
        3.  For the "table", iterate through each row in the SOURCE DATA JSON's table. For each source row, create a new row that fits the BLANK TEMPLATE's table structure.
        4.  The template has columns like 'Description of Parameters' and 'Specified value in mm'. You must intelligently map the data from the source table into these columns. For example, combine 'Specification on drg', 'Std.', and 'UOM' from the source into the 'Specified value in mm' columns of the template.
        5.  The template's 'Observed values' columns should be left as empty strings, as per the template's design.
        """

        print("Executing AI Step 2: Mapping data to template...")
        final_json_string = generate_with_retry(model, prompt_map)
        final_json = json.loads(final_json_string)
        print("AI Step 2 successful. Final report generated.")

        return jsonify(final_json)

    except Exception as e:
        print(f"An error occurred during the two-step AI process: {e}")
        return jsonify({"error": "Failed to generate report from AI model. The document structure may be too complex or the AI failed to map the data."}), 500
    
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
