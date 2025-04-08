import datetime
import logging
import os
import sys
import json
import subprocess
import time
from pathlib import Path
from azure_processing import process_uploaded_financials
from blob_storage import upload_financial_data

# Configure Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Paths
FINANCIAL_DATA_DIR = r"C:\Users\peter\Downloads\FYP - AnM GenAI Benchmaking tool\GenAI-Benchmarking-Tool-for-PortCos\financial_data"
PDF_UPLOAD_DIR = r"C:\Users\peter\Downloads\FYP - AnM GenAI Benchmaking tool\GenAI-Benchmarking-Tool-for-PortCos\test_data"
PROCESSED_DIR = os.path.join(FINANCIAL_DATA_DIR, "processed")
COMPETITOR_ANALYSIS_DIR = r"C:\Users\peter\Downloads\FYP - AnM GenAI Benchmaking tool\GenAI-Benchmarking-Tool-for-PortCos\competitor_analysis"

def upload_pdf():
    """
    Step 1: User provides a PDF, and it's processed using Azure Document Intelligence.
    Returns the path to the processed data and the company name.
    """
    logging.info("📄 Waiting for financial report PDF input...")
    
    # Prompt user for the PDF filename
    pdf_files = [f for f in os.listdir(PDF_UPLOAD_DIR) if f.endswith(".pdf")]
    
    if not pdf_files:
        logging.error("❌ No PDF files found in the directory.")
        sys.exit(1)

    print("\nAvailable Financial Reports:")
    for idx, file in enumerate(pdf_files):
        print(f"{idx + 1}. {file}")

    try:
        choice = int(input("\nSelect a financial report (enter number): ")) - 1
        selected_pdf = pdf_files[choice]
    except (ValueError, IndexError):
        logging.error("❌ Invalid selection. Exiting.")
        sys.exit(1)

    pdf_path = os.path.join(PDF_UPLOAD_DIR, selected_pdf)
    company_name = os.path.splitext(selected_pdf)[0]
    logging.info(f"📂 Selected PDF: {selected_pdf}")

    # Process the PDF with Azure Document Intelligence
    # Ensure the processed directory exists
    os.makedirs(PROCESSED_DIR, exist_ok=True)
    
    # Process the PDF and get the path to the processed data
    try:
        logging.info("🔍 Extracting financial metrics using Azure Document Intelligence...")
        metadata_file, metrics_file = process_uploaded_financials(pdf_path)
        
        # If process_uploaded_financials doesn't return a path, we need to construct it
        if not metrics_file:
            logging.info("🔄 Looking for processed metrics file...")
            # Construct a path where the processed data should be
            company_dir = os.path.join(FINANCIAL_DATA_DIR, company_name.lower().replace(" ", "_"))
            metrics_file = os.path.join(company_dir, f"{company_name.lower().replace(' ', '_')}_financial_metrics.json")
            if not os.path.exists(metrics_file):
                logging.error(f"❌ Could not find financial metrics at {metrics_file}")
                sys.exit(1)
        
        # Load and display basic metrics information for confirmation
        try:
            with open(metrics_file, 'r') as f:
                metrics_data = json.load(f)
                print("\n📊 Extracted Financial Metrics:")
                print(f"  Company: {metrics_data.get('company_name', 'N/A')}")
                print(f"  Industry: {metrics_data.get('industry', 'N/A')}")
                print(f"  Revenue: {metrics_data.get('revenue', 'N/A')} {metrics_data.get('financial_unit', '')}")
                print(f"  Growth Rate: {metrics_data.get('growth_rate', 'N/A')}%")
                print(f"  Employee Count: {metrics_data.get('employee_count', 'N/A')}")
        except Exception as e:
            logging.warning(f"⚠️ Could not display metrics summary: {str(e)}")
        
        logging.info("✅ PDF processed successfully.")
        return metrics_file, company_name
    except Exception as e:
        logging.error(f"❌ Error processing PDF: {str(e)}")
        sys.exit(1)

def identify_competitors_with_perplexity(metrics_file, company_name):
    """
    Step 2: Use Perplexity API to identify competitor companies and fetch their financial data.
    """
    logging.info("🔍 Identifying competitor companies using Perplexity API with financial APIs...")
    
    # Create directory for this company's competitors
    company_slug = company_name.lower().replace(" ", "_")
    competitor_dir = os.path.join(COMPETITOR_ANALYSIS_DIR, company_slug)
    os.makedirs(competitor_dir, exist_ok=True)
    
    # Run the updated Perplexity API script as a subprocess
    perplexity_script = r"C:\Users\peter\Downloads\FYP - AnM GenAI Benchmaking tool\GenAI-Benchmarking-Tool-for-PortCos\src\preplexity_api_competitor_research_with_fin_APIs.py"
    
    try:
        # Check if script exists
        if not os.path.exists(perplexity_script):
            logging.error(f"❌ Perplexity script not found at {perplexity_script}")
            sys.exit(1)
            
        logging.info("🌐 Running Perplexity API competitor finder with financial APIs...")
        print("\n⏳ Starting competitor research. This process may take 20-30 minutes...")
        print("   Progress updates will appear as they occur:\n")
        
        # Run the Perplexity script with the metrics file path as an argument
        # The "-f" flag specifies the file path directly, automating the file selection
        process = subprocess.Popen(
            [sys.executable, perplexity_script, "-f", metrics_file],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=1,
            universal_newlines=True,
            text=True
        )
        
        # Display progress in real-time
        progress_displayed = False
        last_percentage = 0
        progress_markers = {
            "Looking for input company data": 5,
            "Starting competitor analysis": 10,
            "Finding": 15,
            "Sending request to Perplexity API": 20,
            "Received response from Perplexity API": 30,
            "Extracting competitor data": 35,
            "Successfully found": 40,
            "Retrieving financial data": 45,
            "Step 1: Retrieving financial data from APIs": 50,
            "Step 2: Using Perplexity for": 60,
            "Successfully retrieved financial data": 80,
            "Enriching financial data": 85,
            "Saving analysis results": 90,
            "Results are saved in": 95,
            "Analysis complete": 100
        }
        
        # Read and display output in real-time
        for line in iter(process.stdout.readline, ''):
            # Print everything from the Perplexity API script
            print(f"   {line.strip()}")
            
            # Update progress percentage based on recognized keywords
            for marker, percentage in progress_markers.items():
                if marker in line and percentage > last_percentage:
                    last_percentage = percentage
                    progress_displayed = True
                    print(f"\n   [{'=' * (percentage // 5) + '>' + ' ' * (20 - percentage // 5)}] {percentage}% complete\n")
                    break
        
        # Wait for the process to complete
        return_code = process.wait()
        
        if return_code != 0:
            logging.error(f"❌ Perplexity API process failed with return code {return_code}")
            return None, None
        
        logging.info("✅ Perplexity API search completed.")
        
        # Check for output files
        current_date = datetime.datetime.now().strftime("%Y%m%d")
        competitors_file = os.path.join(competitor_dir, f"{company_slug}_competitors_{current_date}.json")
        financials_file = os.path.join(competitor_dir, f"{company_slug}_competitor_financials_{current_date}.json")
        
        # Wait a bit in case files are still being written
        time.sleep(2)
        
        if not os.path.exists(competitors_file) or not os.path.exists(financials_file):
            logging.info("🔍 Looking for alternative competitor files...")
            # Check for any JSON files in the directory as a fallback
            json_files = list(Path(competitor_dir).glob("*.json"))
            if len(json_files) >= 2:
                competitors_candidates = [f for f in json_files if "competitors" in f.name]
                financials_candidates = [f for f in json_files if "financials" in f.name]
                
                if competitors_candidates and financials_candidates:
                    competitors_file = str(competitors_candidates[0])
                    financials_file = str(financials_candidates[0])
                    logging.info(f"Found alternative competitor files: {os.path.basename(competitors_file)} and {os.path.basename(financials_file)}")
                else:
                    logging.warning("⚠️ Could not find expected output files from Perplexity API.")
                    return None, None
            else:
                logging.warning("⚠️ Could not find expected output files from Perplexity API.")
                return None, None
        
        # Display summary of competitors found
        try:
            with open(competitors_file, 'r') as f:
                competitors_data = json.load(f)
                competitors_list = competitors_data.get('competitors', [])
                
                print("\n🏢 Competitor Companies Found:")
                for i, competitor in enumerate(competitors_list, 1):
                    print(f"  {i}. {competitor.get('name', 'Unknown')} ({competitor.get('ticker', 'N/A')})")
                    
            with open(financials_file, 'r') as f:
                financials_data = json.load(f)
                metrics_list = financials_data.get('company_metrics', [])
                
                print(f"\n📊 Financial data retrieved for {len(metrics_list)} companies")
        except Exception as e:
            logging.warning(f"⚠️ Could not display competitors summary: {str(e)}")
        
        logging.info(f"✅ Competitor data saved to {competitor_dir}")
        
        # Return the paths to the competitor and financial data files
        return competitors_file, financials_file
        
    except subprocess.CalledProcessError as e:
        logging.error(f"❌ Error running Perplexity API: {str(e)}")
        if e.stdout:
            logging.info(f"📋 Process output: {e.stdout}")
        if e.stderr:
            logging.error(f"📋 Error output: {e.stderr}")
        return None, None
    except Exception as e:
        logging.error(f"❌ Unexpected error: {str(e)}")
        return None, None

def clean_and_combine_data(metrics_file, competitors_file, financials_file, company_name):
    """
    Step 3: Clean and combine the input company data with competitor data.
    """
    logging.info("🧹 Cleaning and combining financial data...")
    
    # Run the updated data cleaning script as a subprocess
    cleaning_script = r"C:\Users\peter\Downloads\FYP - AnM GenAI Benchmaking tool\GenAI-Benchmarking-Tool-for-PortCos\src\clean_collected_data.py"
    
    try:
        # Check if script exists
        if not os.path.exists(cleaning_script):
            logging.error(f"❌ Data cleaning script not found at {cleaning_script}")
            sys.exit(1)
            
        logging.info("🔄 Running data cleaning and combination process...")
        print("\n⏳ Cleaning and combining competitor data with target company...")
        
        # Create output directory path
        company_slug = company_name.lower().replace(" ", "_")
        output_dir = os.path.join(COMPETITOR_ANALYSIS_DIR, company_slug)
        
        # Run the cleaning script with command line arguments for file paths
        # This passes all necessary information to automate the data cleaning process
        process = subprocess.Popen(
            [sys.executable, cleaning_script, 
             "--metrics", metrics_file, 
             "--competitors", competitors_file, 
             "--financials", financials_file,
             "--output-dir", output_dir],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=1,
            universal_newlines=True,
            text=True
        )
        
        # Display output in real-time
        for line in iter(process.stdout.readline, ''):
            # Print informative lines from the clean_collected_data.py script
            if any(keyword in line for keyword in ["Loading", "Found", "Using", "Saving", "Combining", "Data"]):
                print(f"   {line.strip()}")
        
        # Wait for the process to complete
        return_code = process.wait()
        
        if return_code != 0:
            logging.error(f"❌ Data cleaning process failed with return code {return_code}")
            return None
        
        logging.info("✅ Data cleaning and combination completed.")
        
        # Check for output files
        current_date = datetime.datetime.now().strftime("%Y%m%d")
        
        # Look for the comparison files
        comparison_files = {}
        
        for ext in ["xlsx", "csv", "json", "html"]:
            file_path = os.path.join(output_dir, f"{company_slug}_comparison_{current_date}.{ext}")
            if os.path.exists(file_path):
                comparison_files[ext] = file_path
        
        if not comparison_files:
            # Try a more flexible glob search in case the date format is different
            logging.info("🔍 Looking for alternative comparison files...")
            for ext in ["xlsx", "csv", "json", "html"]:
                comparison_candidates = list(Path(output_dir).glob(f"*_comparison_*.{ext}"))
                if comparison_candidates:
                    # Use the most recent file
                    latest_file = max(comparison_candidates, key=os.path.getmtime)
                    comparison_files[ext] = str(latest_file)
        
        if not comparison_files:
            logging.warning("⚠️ Could not find expected output files from data cleaning process.")
            return None
        
        logging.info(f"✅ Combined data saved as: {', '.join(comparison_files.keys())}")
        
        # Return the paths to the comparison files
        return comparison_files
        
    except subprocess.CalledProcessError as e:
        logging.error(f"❌ Error running data cleaning: {str(e)}")
        if e.stdout:
            logging.info(f"📋 Process output: {e.stdout}")
        if e.stderr:
            logging.error(f"📋 Error output: {e.stderr}")
        return None
    except Exception as e:
        logging.error(f"❌ Unexpected error: {str(e)}")
        return None

def upload_to_blob(comparison_files):
    """
    Step 4: Upload all collected data to Azure Blob Storage.
    """
    logging.info("☁ Uploading financial data to Azure Blob Storage...")
    print("\n⏳ Uploading data to Azure Blob Storage...")
    try:
        upload_financial_data()
        logging.info("✅ Upload completed.")
        print("   ✅ All data successfully uploaded to Azure Blob Storage")
        return True
    except Exception as e:
        logging.error(f"❌ Error uploading to Blob Storage: {str(e)}")
        print(f"   ❌ Error uploading to Azure Blob Storage: {str(e)}")
        return False

def generate_charts(company_name, comparison_files):
    """
    Generate PowerBI-style visualization charts
    """
    logging.info("📈 Generating visualization charts...")
    print("\n⏳ Generating PowerBI-style visualization charts...")
    
    company_slug = company_name.lower().replace(" ", "_")
    competitor_dir = os.path.join(COMPETITOR_ANALYSIS_DIR, company_slug)
    
    # Generate PowerBI-style charts
    charts_script = r"C:\Users\peter\Downloads\FYP - AnM GenAI Benchmaking tool\GenAI-Benchmarking-Tool-for-PortCos\src\generate_PowerBI_graphs.py"
    
    try:
        if not os.path.exists(charts_script):
            logging.warning("⚠️ Charts generation script not found. Skipping charts generation.")
            return None
        
        # Find the CSV file for chart generation
        csv_path = comparison_files.get('csv')
        if not csv_path:
            csv_candidates = list(Path(competitor_dir).glob("*_comparison_*.csv"))
            if csv_candidates:
                csv_path = str(max(csv_candidates, key=os.path.getmtime))
            else:
                logging.error("❌ CSV file not found for charts generation.")
                print("   ❌ CSV file not found for charts generation")
                return None
        
        # Create charts directory path
        charts_dir = os.path.join(competitor_dir, "enhanced_charts")
        
        # Run the charts generation script with automatic mode
        # The "--csv" flag specifies the CSV file path, "--auto" enables automatic mode,
        # and "--output-dir" specifies where to save the charts
        process = subprocess.Popen(
            [sys.executable, charts_script, 
             "--csv", csv_path, 
             "--auto",
             "--output-dir", charts_dir],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )
        
        # Display relevant output
        stdout, _ = process.communicate()
        generated_charts = []
        
        for line in stdout.splitlines():
            if "Saved chart:" in line:
                chart_path = line.split("Saved chart:")[-1].strip()
                chart_name = os.path.basename(chart_path)
                generated_charts.append(chart_path)
                print(f"   📊 Generated chart: {chart_name}")
        
        if process.returncode == 0:
            logging.info("✅ Visualization charts generated successfully.")
            print("   ✅ All charts generated successfully")
            return charts_dir if os.path.exists(charts_dir) else None
        else:
            logging.error(f"❌ Chart generation failed with return code {process.returncode}")
            return None
            
    except Exception as e:
        logging.error(f"❌ Error generating charts: {str(e)}")
        print(f"   ❌ Error generating charts: {str(e)}")
        return None

def generate_report(company_name, comparison_files, charts_dir):
    """
    Generate analysis report that can include charts if available
    """
    logging.info("📊 Generating analysis report...")
    
    company_slug = company_name.lower().replace(" ", "_")
    competitor_dir = os.path.join(COMPETITOR_ANALYSIS_DIR, company_slug)
    
    # Generate report using the generate_report.py script
    report_script = r"C:\Users\peter\Downloads\FYP - AnM GenAI Benchmaking tool\GenAI-Benchmarking-Tool-for-PortCos\src\generate_report.py"
    
    try:
        if not os.path.exists(report_script):
            logging.warning("⚠️ Report generation script not found. Skipping report generation.")
            return
        
        logging.info("📝 Generating analysis report...")
        print("\n⏳ Generating financial analysis report with GPT-4o...")
        
        # Find the CSV file
        csv_file = comparison_files.get('csv')
        if not csv_file:
            # Look for CSV files if not provided directly
            csv_candidates = list(Path(competitor_dir).glob("*_comparison_*.csv"))
            if csv_candidates:
                csv_file = str(max(csv_candidates, key=os.path.getmtime))
            else:
                logging.error("❌ No CSV file found for report generation.")
                print("   ❌ No CSV file found for report generation")
                return
        
        # Prepare command with charts directory if available
        report_cmd = [sys.executable, report_script, "--csv", csv_file, "--auto"]
        
        # Add charts directory parameter if available
        if charts_dir and os.path.exists(charts_dir):
            report_cmd.extend(["--charts-dir", charts_dir])
            logging.info(f"Including charts from {charts_dir} in the report")
            print(f"   📊 Including charts from {os.path.basename(charts_dir)} directory in the report")
            
            # Debug information to help diagnose the issue
            logging.info(f"Charts directory exists: {os.path.exists(charts_dir)}")
            chart_files = list(Path(charts_dir).glob("*.png"))
            logging.info(f"Found {len(chart_files)} PNG files in charts directory")
        
        # Run the report generation script with the command
        logging.info(f"Running command: {' '.join(report_cmd)}")
        process = subprocess.Popen(
            report_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,  # Capture stderr separately
            text=True
        )
        
        # Display relevant output
        stdout, stderr = process.communicate()
        
        # Log any stderr output to help diagnose issues
        if stderr:
            logging.error(f"Report generation stderr: {stderr}")
        
        for line in stdout.splitlines():
            if any(keyword in line for keyword in ["Generating", "Report saved", "Using", "found", "charts"]):
                print(f"   {line}")
        
        if process.returncode == 0:
            logging.info("✅ Analysis report generated successfully.")
            print("   ✅ Financial analysis report completed")
        else:
            logging.error(f"❌ Report generation failed with return code {process.returncode}")
            logging.error(f"Error output: {stderr}")
            print(f"   ❌ Error: {stderr.splitlines()[0] if stderr else 'Unknown error'}")
    except Exception as e:
        logging.error(f"❌ Error generating report: {str(e)}")
        print(f"   ❌ Error generating report: {str(e)}")

def generate_report_and_charts(company_name, comparison_files):
    """
    Step 5: Generate charts first, then generate analysis report with charts
    """
    logging.info("📊 Generating visualizations and analysis report...")
    
    # First generate charts
    charts_dir = generate_charts(company_name, comparison_files)
    
    # Then generate report which can include the charts
    generate_report(company_name, comparison_files, charts_dir)

def main():
    """
    Main function: Handles the entire financial data processing pipeline.
    """
    start_time = datetime.datetime.now()
    logging.info("🚀 Starting Financial Data Processing Pipeline...")
    print("\n" + "="*70)
    print(" FINANCIAL DATA PROCESSING PIPELINE ".center(70, "="))
    print("="*70)

    # Step 1: Process the uploaded PDF
    print("\n📄 STEP 1/5: PDF PROCESSING")
    metrics_file, company_name = upload_pdf()
    logging.info(f"📊 Financial metrics extracted for {company_name}: {metrics_file}")

    # Step 2: Identify competitor companies and get their financials using Perplexity with financial APIs
    print("\n🔍 STEP 2/5: COMPETITOR IDENTIFICATION")
    competitors_file, financials_file = identify_competitors_with_perplexity(metrics_file, company_name)
    
    if not competitors_file or not financials_file:
        logging.error("❌ Failed to get competitor data. Exiting pipeline.")
        print("\n❌ Failed to get competitor data. Pipeline cannot continue.")
        sys.exit(1)
    
    logging.info(f"📈 Competitors identified and their financials retrieved.")

    # Step 3: Clean and combine the data
    print("\n🧹 STEP 3/5: DATA STANDARDIZATION")
    comparison_files = clean_and_combine_data(metrics_file, competitors_file, financials_file, company_name)
    
    if not comparison_files:
        logging.error("❌ Failed to clean and combine data. Exiting pipeline.")
        print("\n❌ Failed to clean and combine data. Pipeline cannot continue.")
        sys.exit(1)
    
    # Step 4: Upload all collected data to Azure Blob Storage
    print("\n☁️ STEP 4/5: DATA STORAGE")
    upload_success = upload_to_blob(comparison_files)
    
    # Step 5: Generate charts first, then reports that can include the charts
    print("\n📊 STEP 5/5: REPORT GENERATION")
    generate_report_and_charts(company_name, comparison_files)
    
    end_time = datetime.datetime.now()
    elapsed_time = end_time - start_time
    hours, remainder = divmod(elapsed_time.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    
    if upload_success:
        logging.info("🏁 Financial Data Pipeline Completed Successfully.")
        
        # Print a summary of the generated files
        print("\n" + "="*70)
        print(" PIPELINE RESULTS ".center(70, "="))
        print("="*70 + "\n")
        print(f"🏢 Company: {company_name}")
        print(f"⏱️ Total Processing Time: {hours}h {minutes}m {seconds}s")
        print(f"\n📑 Financial Metrics: {os.path.basename(metrics_file)}")
        print(f"🏢 Competitors: {os.path.basename(competitors_file)}")
        print(f"📊 Competitor Financials: {os.path.basename(financials_file)}")
        print("\n📋 Comparison Files:")
        for ext, file_path in comparison_files.items():
            print(f"  - {ext.upper()}: {os.path.basename(file_path)}")
        
        # Check for report and chart files
        company_slug = company_name.lower().replace(" ", "_")
        competitor_dir = os.path.join(COMPETITOR_ANALYSIS_DIR, company_slug)
        
        # Check for report file
        report_files = list(Path(competitor_dir).glob("*_report.txt")) + list(Path(competitor_dir).glob("*_analysis.txt"))
        if report_files:
            print("\n📝 Analysis Reports:")
            for report_file in report_files:
                print(f"  - {report_file.name}")
        
        # Check for PDF reports
        pdf_files = list(Path(competitor_dir).glob("*_analysis.pdf")) + list(Path(competitor_dir).glob("*_report.pdf"))
        if pdf_files:
            print("\n📋 PDF Reports:")
            for pdf_file in pdf_files:
                print(f"  - {pdf_file.name}")
        
        # Check for chart files
        charts_dir = os.path.join(competitor_dir, "charts")
        if os.path.exists(charts_dir):
            chart_files = list(Path(charts_dir).glob("*.png"))
            if chart_files:
                print("\n📊 Visualization Charts:")
                print(f"  - {len(chart_files)} charts generated in {os.path.basename(charts_dir)}/")
        
        # Check for enhanced chart files
        enhanced_charts_dir = os.path.join(competitor_dir, "enhanced_charts")
        if os.path.exists(enhanced_charts_dir):
            enhanced_chart_files = list(Path(enhanced_charts_dir).glob("*.png"))
            if enhanced_chart_files:
                print(f"  - {len(enhanced_chart_files)} enhanced charts generated in {os.path.basename(enhanced_charts_dir)}/")
        
        print("\n" + "="*70)
        print(" 🎉 ANALYSIS PIPELINE COMPLETED SUCCESSFULLY 🎉 ".center(70, "="))
        print("="*70)
    else:
        logging.warning("⚠️ Financial Data Pipeline Completed with Warnings (Azure upload failed).")
        print("\n⚠️ Financial Data Pipeline Completed with Warnings (Azure upload failed).")

if __name__ == "__main__":
    main()