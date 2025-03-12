import os
import json
import pandas as pd
from datetime import datetime
import requests
import re
import time
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Azure Document Intelligence configuration - using the correct endpoint format
ENDPOINT = os.getenv("AZURE_DOC_INTELLIGENCE_ENDPOINT").rstrip('/')
API_KEY = os.getenv("AZURE_DOC_INTELLIGENCE_API_KEY")

# PDF file path
PDF_PATH = r"C:\Users\peter\Downloads\FYP - AnM GenAI Benchmaking tool\GenAI-Benchmarking-Tool-for-PortCos\test_data\AstraZeneca_AR_2024_Financial_Statements.pdf"

# Output directory for the extracted financial data
BASE_DIR = r"C:\Users\peter\Downloads\FYP - AnM GenAI Benchmaking tool\GenAI-Benchmarking-Tool-for-PortCos"
OUTPUT_DIR = os.path.join(BASE_DIR, "financial_data", "astrazeneca")

def ensure_directory_exists(directory):
    """Make sure the output directory exists"""
    if not os.path.exists(directory):
        print(f"Creating directory: {directory}")
        os.makedirs(directory)
    print(f"Files will be saved to: {directory}")

def analyze_document(file_path):
    """
    Analyze a PDF document using Azure Document Intelligence
    """
    print(f"Analyzing document: {file_path}")
    
    # Ensure file exists
    if not os.path.exists(file_path):
        print(f"ERROR: File not found: {file_path}")
        return None
    
    print(f"File size: {os.path.getsize(file_path) / 1024:.2f} KB")
    
    # API endpoint - using the correct format from the working example
    analyze_url = f"{ENDPOINT}/formrecognizer/documentModels/prebuilt-document:analyze?api-version=2022-08-31"
    
    # Print the URL for debugging
    print(f"Using API URL: {analyze_url}")
    
    # Request headers
    headers = {
        "Ocp-Apim-Subscription-Key": API_KEY,
        "Content-Type": "application/pdf"
    }
    
    # Read the PDF file
    with open(file_path, "rb") as pdf_file:
        data = pdf_file.read()
    
    # Send the request
    print("Sending request to Azure Document Intelligence...")
    try:
        response = requests.post(analyze_url, headers=headers, data=data)
        
        # Print full response details for debugging
        print(f"Response status code: {response.status_code}")
        
        if response.status_code != 202:
            print(f"Error sending request: {response.status_code}")
            print(response.text)
            return None
        
        # Get operation location for the results
        operation_location = response.headers.get("Operation-Location")
        if not operation_location:
            print("Error: No Operation-Location header in response")
            return None
        
        print(f"Operation location: {operation_location}")
        
        # Wait for the analysis to complete
        print("Waiting for analysis to complete...")
        result = get_analysis_result(operation_location)
        
        return result
        
    except Exception as e:
        print(f"Exception during API request: {str(e)}")
        return None

def get_analysis_result(operation_url):
    """
    Poll for the document analysis result
    """
    headers = {"Ocp-Apim-Subscription-Key": API_KEY}
    max_retries = 30
    wait_time = 5  # seconds
    
    print("⏳ Waiting for document processing...")
    for i in range(max_retries):
        try:
            response = requests.get(operation_url, headers=headers)
            
            if response.status_code != 200:
                print(f"Error fetching results: {response.text}")
                time.sleep(wait_time)
                continue
            
            result = response.json()
            status = result.get("status")
            
            if status == "succeeded":
                print("✅ Processing completed successfully!")
                return result
            elif status == "failed":
                print(f"Analysis failed: {result}")
                return None
            else:
                print(f"⏳ Analysis in progress... (attempt {i+1}/{max_retries})")
                time.sleep(wait_time)
            
        except Exception as e:
            print(f"Error polling for results: {str(e)}")
            time.sleep(wait_time)
    
    print("Maximum retries reached. Analysis may still be in progress.")
    return None

def extract_tables_from_analysis(analysis_result):
    """
    Extract tables from the document analysis result
    """
    if not analysis_result:
        print("No valid analysis result to extract tables from")
        return []
    
    tables = []
    
    # Check if document has tables in the response
    if 'analyzeResult' in analysis_result and 'tables' in analysis_result['analyzeResult']:
        raw_tables = analysis_result['analyzeResult']['tables']
        
        for i, table in enumerate(raw_tables):
            # Extract the rows and columns from the table
            rows = table.get('rowCount', 0)
            cols = table.get('columnCount', 0)
            
            if rows == 0 or cols == 0:
                print(f"Table {i} has invalid dimensions: {rows}x{cols}")
                continue
            
            # Create an empty grid
            grid = [[None for _ in range(cols)] for _ in range(rows)]
            
            # Fill in the grid
            for cell in table.get('cells', []):
                row_index = cell.get('rowIndex', 0)
                col_index = cell.get('columnIndex', 0)
                text = cell.get('content', '')
                
                if row_index < rows and col_index < cols:
                    grid[row_index][col_index] = text
            
            # Convert to DataFrame
            df = pd.DataFrame(grid)
            
            # All tables from financial reports are potentially interesting
            tables.append({
                'index': i,
                'table': df,
                'raw_data': table,
                'page': table.get('pageNumber', 0)
            })
    
    print(f"Extracted {len(tables)} tables from document")
    
    # If no tables were found, try to extract financial data using KPI extraction
    if not tables:
        print("No tables found. Attempting to extract financial KPIs directly...")
        financial_data = extract_financial_kpis(analysis_result)
        
        if financial_data:
            # Convert extracted KPIs to a DataFrame that looks like a table
            kpi_df = pd.DataFrame.from_dict(financial_data, orient='index', columns=['Value'])
            kpi_df.reset_index(inplace=True)
            kpi_df.columns = ['Metric', 'Value']
            
            tables.append({
                'index': 0,
                'table': kpi_df,
                'raw_data': None,
                'page': 0,
                'is_kpi_extraction': True
            })
    
    return tables

def extract_financial_kpis(analysis_result):
    """
    Extracts key financial KPIs from Azure Document Intelligence output.
    Since data is not structured, we extract numbers based on keywords.
    Returns a structured dictionary.
    """
    if not analysis_result or 'analyzeResult' not in analysis_result:
        print("No valid analysis result for KPI extraction")
        return None

    # Define common financial KPI keywords
    key_terms = [
        "Total Revenue", "Revenue", "Net Income", "Operating Income", "Profit",
        "R&D Expense", "Research & Development", "EBITDA", "Earnings Per Share",
        "EPS", "Diluted EPS", "Basic EPS", "Cost of Revenue", "Gross Profit",
        "Total Assets", "Total Liabilities", "Cash and Cash Equivalents"
    ]

    try:
        # Convert all extracted words into a single text string for easy searching
        full_text = " ".join(word["content"] for page in analysis_result["analyzeResult"]["pages"] 
                            for word in page.get("words", []))

        # Extract financial KPIs by finding numbers after key financial terms
        financial_data = {}

        for term in key_terms:
            # Search for the term followed by a number (handles formats like "Revenue 54,073,000")
            match = re.search(rf"{term}[\s:]*([\d,]+\.?\d*)", full_text, re.IGNORECASE)

            if match:
                financial_data[term] = match.group(1)
            else:
                # Try alternative search pattern (number followed by term)
                match = re.search(rf"([\d,]+\.?\d*)[\s:]*{term}", full_text, re.IGNORECASE)
                if match:
                    financial_data[term] = match.group(1)
                else:
                    financial_data[term] = "N/A"

        return financial_data
    except Exception as e:
        print(f"Error extracting KPIs: {str(e)}")
        return None

def identify_financial_statements(tables):
    """
    Identify and categorize financial statement tables
    """
    financial_statements = {
        'income_statement': None,
        'balance_sheet': None,
        'cash_flow': None
    }
    
    # If we only have KPI data, create a combined statement
    if len(tables) == 1 and tables[0].get('is_kpi_extraction', False):
        # Use the KPI extraction for all statement types
        financial_statements['income_statement'] = tables[0]
        financial_statements['balance_sheet'] = tables[0]
        financial_statements['cash_flow'] = tables[0]
        print("Using extracted KPI data for financial statements")
        return financial_statements
    
    # Keywords to identify each statement type
    income_keywords = ['profit', 'loss', 'revenue', 'income statement', 'operating', 'earnings']
    balance_keywords = ['balance sheet', 'assets', 'liabilities', 'equity']
    cashflow_keywords = ['cash flow', 'operating activities', 'investing activities', 'financing activities']
    
    for table_info in tables:
        table = table_info['table']
        table_text = ' '.join([str(cell) for row in table.values for cell in row if cell])
        table_text = table_text.lower()
        
        # Check for income statement
        income_score = sum(table_text.count(kw) for kw in income_keywords)
        balance_score = sum(table_text.count(kw) for kw in balance_keywords)
        cashflow_score = sum(table_text.count(kw) for kw in cashflow_keywords)
        
        if income_score > balance_score and income_score > cashflow_score and financial_statements['income_statement'] is None:
            financial_statements['income_statement'] = table_info
            print(f"Identified Income Statement (table {table_info['index']} on page {table_info['page']})")
        elif balance_score > income_score and balance_score > cashflow_score and financial_statements['balance_sheet'] is None:
            financial_statements['balance_sheet'] = table_info
            print(f"Identified Balance Sheet (table {table_info['index']} on page {table_info['page']})")
        elif cashflow_score > income_score and cashflow_score > balance_score and financial_statements['cash_flow'] is None:
            financial_statements['cash_flow'] = table_info
            print(f"Identified Cash Flow Statement (table {table_info['index']} on page {table_info['page']})")
    
    return financial_statements

def clean_table(table_df):
    """
    Clean and structure a financial table
    """
    # Check if this is a KPI extraction (already clean)
    if 'Metric' in table_df.columns and 'Value' in table_df.columns:
        return table_df
    
    # Make a copy to avoid modifying the original
    df = table_df.copy()
    
    # Remove completely empty rows and columns
    df = df.dropna(how='all').dropna(axis=1, how='all')
    
    # Try to identify header row (if not the first row)
    # In financial statements, the header row often contains years
    year_pattern = re.compile(r'\b(20\d\d|20\d{2})\b')
    header_row = 0
    
    for i, row in df.iterrows():
        # Count cells that look like years in this row
        year_cells = sum(1 for cell in row if isinstance(cell, str) and year_pattern.search(str(cell)))
        if year_cells >= 2:  # If multiple year cells are found, this is likely a header row
            header_row = i
            break
    
    # Extract headers and create a new DataFrame
    if header_row > 0:
        headers = df.iloc[header_row].tolist()
        data = df.iloc[header_row+1:].reset_index(drop=True)
    else:
        headers = df.iloc[0].tolist()
        data = df.iloc[1:].reset_index(drop=True)
    
    # Clean headers (replace None with index)
    headers = [f"Column_{i}" if pd.isna(h) else str(h) for i, h in enumerate(headers)]
    
    # Ensure headers are unique
    unique_headers = []
    for h in headers:
        if h in unique_headers:
            i = 1
            while f"{h}_{i}" in unique_headers:
                i += 1
            unique_headers.append(f"{h}_{i}")
        else:
            unique_headers.append(h)
    
    # Create clean DataFrame with proper headers
    clean_df = pd.DataFrame(data.values, columns=unique_headers)
    
    # Try to identify the first column as the index (metrics/line items)
    if len(clean_df.columns) > 1:
        clean_df.set_index(clean_df.columns[0], inplace=True)
    
    return clean_df

def process_financial_statements(financial_statements):
    """
    Process and clean the identified financial statements
    """
    processed_statements = {}
    
    for name, table_info in financial_statements.items():
        if table_info is not None:
            # Clean and process the table
            processed_df = clean_table(table_info['table'])
            processed_statements[name] = processed_df
            print(f"Processed {name} statement")
        else:
            print(f"No {name} statement identified")
    
    return processed_statements

def save_financials_to_csv(financials, output_dir, prefix="astrazeneca_"):
    """
    Save financial dataframes to CSV files.
    """
    saved_files = []
    for name, df in financials.items():
        if df is not None and not df.empty:
            filename = os.path.join(output_dir, f"{prefix}{name}.csv")
            df.to_csv(filename)
            print(f"Saved {filename}")
            saved_files.append({"type": name, "format": "csv", "filename": os.path.basename(filename)})
    return saved_files

def save_financials_to_json(financials, output_dir, prefix="astrazeneca_"):
    """
    Save financial dataframes to JSON files.
    """
    saved_files = []
    for name, df in financials.items():
        if df is not None and not df.empty:
            # Convert DataFrame to JSON-friendly format
            json_data = json.loads(df.reset_index().to_json(orient='records'))
            
            filename = os.path.join(output_dir, f"{prefix}{name}.json")
            with open(filename, 'w') as f:
                json.dump(json_data, f, indent=4)
            print(f"Saved {filename}")
            saved_files.append({"type": name, "format": "json", "filename": os.path.basename(filename)})
    return saved_files

def create_metadata_json(csv_files, json_files, output_dir, prefix="astrazeneca_"):
    """
    Create a metadata JSON file with information about all saved files
    and the date of retrieval.
    """
    # Get PDF file information
    pdf_file = Path(PDF_PATH)
    pdf_info = {
        "filename": pdf_file.name,
        "size_bytes": pdf_file.stat().st_size,
        "last_modified": datetime.fromtimestamp(pdf_file.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
    }
    
    metadata = {
        "company": "AstraZeneca",
        "source": "Annual Report PDF",
        "pdf_info": pdf_info,
        "extraction_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "files": {
            "csv": csv_files,
            "json": json_files
        }
    }
    
    filename = os.path.join(output_dir, f"{prefix}metadata.json")
    with open(filename, 'w') as f:
        json.dump(metadata, f, indent=4)
    print(f"Saved {filename}")
    return filename

def save_raw_analysis(analysis_result, output_dir):
    """
    Save the raw analysis result for debugging purposes
    """
    filename = os.path.join(output_dir, "azure_response.json")
    with open(filename, 'w') as f:
        json.dump(analysis_result, f, indent=4)
    print(f"Saved raw analysis to {filename}")

def process_uploaded_financials(pdf_path):
    """
    Wrapper function to process a financial report PDF.
    It extracts financial data and saves it in the appropriate folder.
    """
    ensure_directory_exists(OUTPUT_DIR)

    print("\n🚀 Starting Azure Document Intelligence processing...")
    
    # Analyze the uploaded PDF
    analysis_result = analyze_document(pdf_path)
    
    if analysis_result:
        # Save the raw analysis response
        save_raw_analysis(analysis_result, OUTPUT_DIR)
        
        # Extract tables from the analysis result
        tables = extract_tables_from_analysis(analysis_result)
        
        if tables:
            # Identify financial statements
            financial_statements = identify_financial_statements(tables)
            
            # Process and clean financial statements
            processed_statements = process_financial_statements(financial_statements)
            
            # Save as CSV
            csv_files = save_financials_to_csv(processed_statements, OUTPUT_DIR)
            
            # Save as JSON
            json_files = save_financials_to_json(processed_statements, OUTPUT_DIR)
            
            # Create metadata JSON
            metadata_file = create_metadata_json(csv_files, json_files, OUTPUT_DIR)
            
            print(f"\n✅ Financial data extracted and saved in: {OUTPUT_DIR}")
            print(f"📄 Metadata file created: {metadata_file}")
        else:
            print("❌ No tables detected in the document analysis.")
    else:
        print("❌ Azure Document Intelligence failed to process the document.")

if __name__ == "__main__":
    # Ensure the output directory exists
    ensure_directory_exists(OUTPUT_DIR)
    
    print("\n🚀 Starting Azure Document Intelligence processing...")
    
    # Analyze the PDF document
    analysis_result = analyze_document(PDF_PATH)
    
    if analysis_result:
        # Save the raw analysis for debugging
        save_raw_analysis(analysis_result, OUTPUT_DIR)
        
        # Extract tables from the analysis result
        tables = extract_tables_from_analysis(analysis_result)
        
        if tables:
            # Identify financial statements
            financial_statements = identify_financial_statements(tables)
            
            # Process financial statements
            processed_statements = process_financial_statements(financial_statements)
            
            # Save to CSV files
            csv_files = save_financials_to_csv(processed_statements, OUTPUT_DIR)
            
            # Save to JSON files
            json_files = save_financials_to_json(processed_statements, OUTPUT_DIR)
            
            # Create metadata JSON
            metadata_file = create_metadata_json(csv_files, json_files, OUTPUT_DIR)
            
            print(f"\n✅ Complete! Financial data has been extracted and saved to CSV and JSON files in: {OUTPUT_DIR}")
            print(f"📄 Metadata file with all information: {metadata_file}")
        else:
            print("❌ No tables found in the document analysis")
    else:
        print("❌ Document analysis failed")