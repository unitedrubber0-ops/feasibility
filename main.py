# main.py - FINAL SIMPLIFIED VERSION

import os
import io
import json
import time
import PyPDF2
import docx
import google.generativeai as genai
import google.api_core.exceptions
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS

# --- Helper function to extract text page by page ---
def extract_text_from_pdf_paginated(file_stream):
    """Reads a PDF file stream and returns a list of text content, one string per page."""
    try:
        pdf_reader = PyPDF2.PdfReader(file_stream)
        pages_text = []
        for page in pdf_reader.pages:
            pages_text.append(page.extract_text() or "")
        return pages_text
    except Exception as e:
        print(f"Error reading PDF paginated: {e}")
        return None

# --- Existing helper functions (no changes needed) ---
def extract_text_from_docx(file_stream):
    """Reads a DOCX file stream and returns its text content."""
    try:
        document = docx.Document(file_stream)
        return "\n".join([para.text for para in document.paragraphs])
    except Exception as e:
        print(f"Error reading DOCX: {e}")
        return None

def generate_with_retry(model, prompt, max_retries=3, retry_delay=5):
    """Calls the Gemini API with a given prompt and handles retries."""
    for attempt in range(max_retries):
        try:
            response = model.generate_content(prompt)
            cleaned_text = response.text.strip().replace("```json", "").replace("```", "")
            json.loads(cleaned_text) # Validate JSON before returning
            return cleaned_text
        except Exception as e:
            print(f"Error on attempt {attempt + 1}: {e}. Retrying...")
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
            else:
                raise e

# --- Flask App Initialization ---
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": ["https://feasibility-1.onrender.com", "http://127.0.0.1:5001"]}})

# --- Gemini API Configuration ---
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# --- Main API Endpoint ---
@app.route('/generate-report', methods=['POST'])
def generate_report_handler():
    """
    Handles the report generation by parsing the source file page-by-page.
    """
    print("Received request to /generate-report")
    if 'sourceFile' not in request.files:
        return jsonify({"error": "Source file is missing"}), 400

    source_file = request.files['sourceFile']

    try:
        source_stream = io.BytesIO(source_file.read())
        source_pages = []
        if source_file.filename.endswith('.pdf'):
            source_pages = extract_text_from_pdf_paginated(source_stream)
        elif source_file.filename.endswith('.docx'):
            source_text = extract_text_from_docx(source_stream)
            source_pages.append(source_text)
        else: # Handle TXT, MD, etc.
            source_text = source_stream.read().decode('utf-8', errors='ignore')
            source_pages.append(source_text)
        
        if not source_pages:
            return jsonify({"error": "Could not extract text from the source file."}), 500
    except Exception as e:
        print(f"Error during file processing: {e}")
        return jsonify({"error": "Failed to process files"}), 500

    try:
        if not GEMINI_API_KEY:
             return jsonify({"error": "Gemini API key is not configured."}), 500

        safety_settings = [{"category": c, "threshold": "BLOCK_NONE"} for c in ["HARM_CATEGORY_HARASSMENT", "HARM_CATEGORY_HATE_SPEECH", "HARM_CATEGORY_SEXUALLY_EXPLICIT", "HARM_CATEGORY_DANGEROUS_CONTENT"]]
        generation_config = genai.GenerationConfig(max_output_tokens=8192, temperature=0.1)
        model = genai.GenerativeModel("gemini-2.5-pro", generation_config=generation_config, safety_settings=safety_settings)

        # --- This function is now the final step ---
        # It aggregates data from all pages into a single structured object.
        aggregated_header = {}
        aggregated_rows = []
        table_columns = None

        prompt_extract_template = """
        You are an expert data extraction assistant. Analyze the DOCUMENT PAGE text and extract its header and table data into a JSON format.

        **DOCUMENT PAGE:**
        ---
        {page_text}
        ---

        **INSTRUCTIONS:**
        1. Return a single raw JSON object with "header" and "table" keys.
        2. If this page contains header-like data (e.g., Customer Name, Report Number), put it in the "header" object.
        3. If this page contains a table or part of a table, put its data in the "table" object, which must have "columns" and "rows".
        4. If no table is present on this page, return an empty list for "rows".
        5. The "rows" should accurately reflect the structure on the page. If one item spans multiple lines (like 'Thickness'), combine them into a single logical row in the JSON.
        """

        for i, page_text in enumerate(source_pages):
            print(f"Executing AI on page {i + 1}/{len(source_pages)}...")
            if not page_text.strip():
                print(f"Skipping empty page {i + 1}.")
                continue
            
            prompt = prompt_extract_template.format(page_text=page_text)
            extracted_json_string = generate_with_retry(model, prompt)
            page_json = json.loads(extracted_json_string)

            if page_json.get("header"):
                aggregated_header.update(page_json["header"])
            
            if page_json.get("table") and page_json["table"].get("rows"):
                # Capture the column headers from the first page that has them
                if table_columns is None and page_json["table"].get("columns"):
                    table_columns = page_json["table"]["columns"]
                aggregated_rows.extend(page_json["table"]["rows"])
        
        if table_columns is None: table_columns = []
        
        # Combine all extracted data into the final result
        final_report_json = {"header": aggregated_header, "table": {"columns": table_columns, "rows": aggregated_rows}}
        print("AI extraction complete for all pages. Sending final report.")

        return jsonify(final_report_json)

    except Exception as e:
        print(f"An error occurred during the AI process: {e}")
        return jsonify({"error": "Failed to generate report from AI model."}), 500

# --- The /export-docx endpoint remains unchanged ---
@app.route('/export-docx', methods=['POST'])
def export_docx_handler():
    """
    Receives report data in JSON format and returns a DOCX file.
    """
    data = request.get_json()
    try:
        document = docx.Document()
        document.add_heading('Inspection Report', level=1)
        
        if data.get("header"):
            for key, value in data.get('header', {}).items():
                document.add_paragraph(f"{key}: {value}")
        
        document.add_paragraph()
        
        if data.get("table"):
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
    app.run(debug=True, port=5001)