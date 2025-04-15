import os
import json
import time
import threading
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_from_directory, send_file
from werkzeug.utils import secure_filename
import subprocess
import logging
import sys

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Setup paths
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'test_data')
RESULTS_FOLDER = os.path.join(BASE_DIR, 'competitor_analysis')
FINANCIAL_DATA_DIR = os.path.join(BASE_DIR, 'financial_data')

# Ensure directories exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(RESULTS_FOLDER, exist_ok=True)
os.makedirs(FINANCIAL_DATA_DIR, exist_ok=True)

# Initialize Flask app
app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max upload
app.config['COMPETITOR_ANALYSIS_DIR'] = RESULTS_FOLDER
app.secret_key = 'financial-competitor-finder-secret-key'

# Global variables to track process status
current_process = None
process_status = {
    'running': False,
    'company_name': None,
    'status': 'idle',
    'progress': 0,
    'messages': [],
    'results': {}
}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() == 'pdf'

def run_financial_analysis(pdf_path):
    """Run the main.py script as a subprocess with the uploaded PDF"""
    global process_status

    try:
        # Reset process status
        process_status['running'] = True
        process_status['status'] = 'processing'
        process_status['progress'] = 0
        process_status['messages'] = ['Starting financial analysis...']

        # Get company name from filename
        company_name = os.path.splitext(os.path.basename(pdf_path))[0]
        process_status['company_name'] = company_name

        logging.info(f"[DEBUG] Host PDF path: {pdf_path}")
        logging.info(f"[DEBUG] File exists on host: {os.path.exists(pdf_path)}")

        # Create command to run main.py inside Docker context
        cmd = [sys.executable, os.path.join(BASE_DIR, 'src', 'main.py')]

        # Paths used inside Docker container
        container_pdf_path = os.path.join('/app', 'test_data', os.path.basename(pdf_path))
        container_upload_folder = '/app/test_data'
        container_financial_data = '/app/financial_data'
        container_results_folder = '/app/competitor_analysis'

        logging.info(f"[DEBUG] Mapped Docker PDF path: {container_pdf_path}")
        logging.info(f"[DEBUG] Mapped Docker Upload Dir: {container_upload_folder}")
        logging.info(f"[DEBUG] Mapped Docker Results Dir: {container_results_folder}")

        # Set environment variables for subprocess
        env = os.environ.copy()
        env['SELECTED_PDF'] = container_pdf_path
        env['PDF_UPLOAD_DIR'] = container_upload_folder
        env['FINANCIAL_DATA_DIR'] = container_financial_data
        env['COMPETITOR_ANALYSIS_DIR'] = container_results_folder

        # Run the subprocess
        process = subprocess.Popen(
            cmd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=1,
            universal_newlines=True,
            text=True
        )

        logging.info(f"[DEBUG] Launched subprocess: {cmd}")

        # Process progress markers for status updates
        progress_markers = {
            "Extracting financial metrics": 10,
            "PDF processed successfully": 15,
            "Identifying competitor companies": 20,
            "Running Perplexity API": 25,
            "Starting competitor research": 30,
            "Finding competitors": 35,
            "Received response from Perplexity API": 40,
            "Extracting competitor data": 45,
            "Retrieving financial data": 50,
            "Successfully retrieved financial data": 60,
            "Cleaning and combining financial data": 65,
            "Data cleaning and combination completed": 70,
            "Uploading financial data": 75,
            "Upload completed": 80,
            "Generating visualization charts": 85,
            "Generating analysis report": 90,
            "Financial analysis report completed": 95,
            "ANALYSIS PIPELINE COMPLETED SUCCESSFULLY": 100
        }

        for line in iter(process.stdout.readline, ''):
            line = line.strip()
            logging.info(f"[PIPELINE OUTPUT] {line}")
            process_status['messages'].append(line)
            for marker, percentage in progress_markers.items():
                if marker in line and percentage > process_status['progress']:
                    process_status['progress'] = percentage
                    process_status['status'] = f"Step {percentage}% complete"
                    break

        process.wait()

        if process.returncode == 0:
            process_status['status'] = 'completed'
            process_status['progress'] = 100

            company_slug = company_name.lower().replace(" ", "_")
            results_dir = os.path.join(RESULTS_FOLDER, company_slug)
            charts_dir = os.path.join(results_dir, "enhanced_charts")
            report_files = [f for f in os.listdir(results_dir) if f.endswith('_report.txt') or f.endswith('_analysis.txt')]
            comparison_files = [f for f in os.listdir(results_dir) if f.endswith('.csv') or f.endswith('.xlsx') or f.endswith('.json')]

            charts = []
            if os.path.exists(charts_dir):
                charts = [f for f in os.listdir(charts_dir) if f.endswith('.png')]

            process_status['results'] = {
                'company_name': company_name,
                'company_slug': company_slug,
                'charts': charts,
                'reports': report_files,
                'comparison_files': comparison_files,
                'timestamp': time.strftime('%Y-%m-%d %H:%M:%S')
            }

            process_status['messages'].append("Analysis completed successfully!")
        else:
            process_status['status'] = 'error'
            process_status['messages'].append("Error: Process failed with non-zero exit code")
            logging.error("❌ Subprocess returned non-zero exit code")

    except Exception as e:
        process_status['status'] = 'error'
        error_msg = f"Error in analysis thread: {str(e)}"
        process_status['messages'].append(f"Error: {error_msg}")
        logging.error(error_msg)

    finally:
        process_status['running'] = False

@app.route('/')
def index():
    """Main page - upload form and status display"""
    # Get list of available PDFs
    pdf_files = [f for f in os.listdir(UPLOAD_FOLDER) if f.endswith('.pdf')]
    
    # Get list of completed analyses
    completed_analyses = []
    for company_dir in os.listdir(RESULTS_FOLDER):
        if os.path.isdir(os.path.join(RESULTS_FOLDER, company_dir)):
            completed_analyses.append({
                'company_name': company_dir.replace('_', ' ').title(),
                'company_slug': company_dir,
                'timestamp': time.strftime('%Y-%m-%d', 
                              time.gmtime(os.path.getmtime(os.path.join(RESULTS_FOLDER, company_dir))))
            })
    
    return render_template('index.html', 
                          pdf_files=pdf_files, 
                          process_status=process_status,
                          completed_analyses=completed_analyses)

@app.route('/upload', methods=['POST'])
def upload_file():
    """Handle PDF file upload"""
    if 'file' not in request.files:
        flash('No file part')
        return redirect(request.url)
    
    file = request.files['file']
    
    if file.filename == '':
        flash('No selected file')
        return redirect(request.url)
    
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)
        flash(f'File {filename} uploaded successfully')
        return redirect(url_for('index'))
    
    flash('Invalid file format. Please upload a PDF file.')
    return redirect(url_for('index'))

@app.route('/analyze', methods=['POST'])
def analyze():
    """Start analysis process for selected PDF"""
    global current_process, process_status
    
    # Check if a process is already running
    if process_status['running']:
        flash('Analysis already in progress. Please wait until it completes.')
        return redirect(url_for('index'))
    
    # Get selected PDF from form
    selected_pdf = request.form.get('selected_pdf')
    
    if not selected_pdf:
        flash('No PDF selected')
        return redirect(url_for('index'))
    
    pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], selected_pdf)
    
    if not os.path.exists(pdf_path):
        flash('Selected PDF file not found')
        return redirect(url_for('index'))
    
    # Start the analysis in a separate thread
    current_process = threading.Thread(target=run_financial_analysis, args=(pdf_path,))
    current_process.daemon = True
    current_process.start()
    
    flash(f'Analysis started for {selected_pdf}')
    return redirect(url_for('index'))

@app.route('/status')
def status():
    """Return current process status as JSON"""
    return jsonify(process_status)

@app.route('/results/<company_slug>')
def results(company_slug):
    """Show results page for a completed analysis"""
    company_dir = os.path.join(RESULTS_FOLDER, company_slug)
    
    if not os.path.exists(company_dir):
        flash('Results not found')
        return redirect(url_for('index'))
    
    # Collect result files
    charts_dir = os.path.join(company_dir, "enhanced_charts")
    
    # Look for both text and PDF reports
    report_files = [f for f in os.listdir(company_dir) if 
                   f.endswith('_report.txt') or 
                   f.endswith('_analysis.txt') or 
                   f.endswith('_report.pdf') or 
                   f.endswith('_analysis.pdf')]
    
    comparison_files = [f for f in os.listdir(company_dir) if f.endswith('.csv') or f.endswith('.xlsx') or f.endswith('.json')]
    
    # Check for charts
    charts = []
    if os.path.exists(charts_dir):
        charts = [f for f in os.listdir(charts_dir) if f.endswith('.png')]
    
    # Get report content if available (text reports only)
    report_content = None
    for report in report_files:
        if report.endswith('.txt'):
            with open(os.path.join(company_dir, report), 'r') as f:
                report_content = f.read()
            break
    
    results_data = {
        'company_name': company_slug.replace('_', ' ').title(),
        'company_slug': company_slug,
        'charts': charts,
        'reports': report_files,
        'report_content': report_content,
        'comparison_files': comparison_files,
        'timestamp': time.strftime('%Y-%m-%d', 
                    time.gmtime(os.path.getmtime(company_dir)))
    }
    
    return render_template('results.html', results=results_data)

@app.route('/download/<path:filename>')
def download_file(filename):
    """Download a result file"""
    directory = os.path.dirname(filename)
    file = os.path.basename(filename)
    return send_from_directory(os.path.join(BASE_DIR, directory), file, as_attachment=True)

@app.route('/chart/<company_slug>/<chart_file>')
def get_chart(company_slug, chart_file):
    """Serve chart image"""
    charts_dir = os.path.join(RESULTS_FOLDER, company_slug, "enhanced_charts")
    return send_from_directory(charts_dir, chart_file)


@app.route('/get_pdf/<company_slug>/<pdf_file>')
def get_pdf(company_slug, pdf_file):
    """
    Serve a PDF file from the competitor analysis folder.
    This allows embedding PDFs in an iframe on the results page.
    """
    pdf_path = os.path.join(app.config['COMPETITOR_ANALYSIS_DIR'], company_slug, pdf_file)
    
    if not os.path.exists(pdf_path):
        return "PDF not found", 404
        
    return send_file(pdf_path, mimetype='application/pdf')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)