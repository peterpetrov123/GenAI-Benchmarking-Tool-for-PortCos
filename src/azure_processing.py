import os
import json
import pandas as pd
from datetime import datetime
import requests
import re
import time
from pathlib import Path
from dotenv import load_dotenv


load_dotenv()

# Azure Document Intelligence configuration 
ENDPOINT = os.getenv("AZURE_DOC_INTELLIGENCE_ENDPOINT").rstrip('/')
API_KEY = os.getenv("AZURE_DOC_INTELLIGENCE_API_KEY")

# PDF file path
PDF_PATH = r"C:\Users\peter\Downloads\FYP - AnM GenAI Benchmaking tool\GenAI-Benchmarking-Tool-for-PortCos\test_data\AstraZeneca_AR_2024_Financial_Statements.pdf"

# Output directory for the extracted financial data
BASE_DIR = r"C:\Users\peter\Downloads\FYP - AnM GenAI Benchmaking tool\GenAI-Benchmarking-Tool-for-PortCos"
OUTPUT_DIR = os.path.join(BASE_DIR, "financial_data", "astrazeneca")

FINANCIAL_DATA_DIR = r"C:\Users\peter\Downloads\FYP - AnM GenAI Benchmaking tool\GenAI-Benchmarking-Tool-for-PortCos\financial_data"

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
    import os
    from pathlib import Path
    from datetime import datetime
    import json
    
    # Get the actual PDF path that was used for processing
    # Instead of using the hardcoded PDF_PATH, use the provided pdf_path parameter
    pdf_filename = ""
    pdf_size = 0
    pdf_modified = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Try to determine PDF info from the first part of the generated path
    if prefix:
        try:
            pdf_filename = prefix.replace("_", " ").strip()
            if pdf_filename.endswith(".pdf"):
                pdf_filename = pdf_filename
            else:
                pdf_filename = f"{pdf_filename}.pdf"
        except:
            pdf_filename = "Unknown"
    
    # Check if we're running in Docker
    running_in_docker = os.path.exists("/.dockerenv") or os.environ.get("DOCKERIZED") == "1"
    
    pdf_info = {
        "filename": pdf_filename,
        "size_bytes": pdf_size,  # We'll leave this as 0 since we can't reliably get it
        "last_modified": pdf_modified
    }
    
    # Extract company name from the prefix
    company_name = "Unknown"
    if prefix:
        company_name = prefix.split("_")[0].capitalize()
    
    metadata = {
        "company": company_name,
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

def extract_key_financial_metrics(processed_statements, company_name, output_dir):
    """
    Extract key financial metrics from processed financial statements
    and save them in a structured format required for competitor analysis.
    Works with any company's financial data and automatically detects
    currency and scale.
    
    Args:
        processed_statements: Dictionary containing processed financial statements
        company_name: Name of the company
        output_dir: Directory to save the output file
        
    Returns:
        Path to the saved metrics JSON file
    """
    import os
    import json
    import re
    import pandas as pd
    import numpy as np
    from pathlib import Path
    
    print("Extracting key financial metrics for competitor analysis...")
    
    # Initialize metrics dictionary with default values
    metrics = {
        "company_name": company_name,
        "industry": "N/A",
        "business_model": "N/A",
        "revenue": "N/A",
        "growth_rate": "N/A",
        "gross_margin": "N/A",
        "ebitda_margin": "N/A",
        "rd_percentage": "N/A",
        "employee_count": "N/A",
        "key_products_services": "N/A",
        "financial_unit": "N/A"
    }
    
    # Determine the currency and scale from the financial statements
    currency = "EUR"  # Default for European market
    scale = "millions"  # Default scale
    
    # Try to detect currency and scale from the statements
    for statement_type in ["income_statement", "balance_sheet"]:
        if statement_type in processed_statements and processed_statements[statement_type] is not None:
            df = processed_statements[statement_type]
            
            # Look for currency and scale indicators in both column headers and data
            all_text = ' '.join([str(x) for x in df.columns] + [str(x) for x in df.index])
            all_text = all_text.lower()
            
            # Currency detection
            if "$" in all_text or "usd" in all_text or "dollar" in all_text:
                currency = "USD"
            elif "€" in all_text or "eur" in all_text or "euro" in all_text:
                currency = "EUR"
            elif "£" in all_text or "gbp" in all_text or "pound" in all_text:
                currency = "GBP"
            
            # Scale detection
            if "million" in all_text or " m " in all_text or "m$" in all_text or "m€" in all_text or "m£" in all_text:
                scale = "millions"
            elif "billion" in all_text or " b " in all_text or "b$" in all_text or "b€" in all_text or "b£" in all_text:
                scale = "billions"
            elif "thousand" in all_text or " k " in all_text or "k$" in all_text or "k€" in all_text or "k£" in all_text:
                scale = "thousands"
    
    # Set the detected unit
    metrics["financial_unit"] = f"{currency} {scale}"
    
    # Helper function to safely convert a value to float
    def safe_float(value):
        if isinstance(value, (int, float)):
            return float(value)
        elif isinstance(value, str):
            # Remove all non-numeric characters except decimals and negatives
            clean_value = re.sub(r'[^0-9.-]', '', value)
            try:
                return float(clean_value)
            except ValueError:
                return None
        return None
    
    # Helper function to find values in financial statements
    def find_value(statement_type, search_terms, year_column=None, fallback_columns=None):
        if statement_type not in processed_statements or processed_statements[statement_type] is None:
            return None
            
        df = processed_statements[statement_type]
        
        # If no specific columns provided, use the first and second columns
        if year_column is None:
            if len(df.columns) > 0:
                year_column = df.columns[0]
            else:
                return None
        
        if fallback_columns is None:
            if len(df.columns) > 1:
                fallback_columns = df.columns[1:]
            else:
                fallback_columns = []
        
        # Convert DataFrame index to string for easier searching
        df.index = df.index.map(str)
        
        # Try each search term
        for term in search_terms:
            # Case-insensitive search in the index
            matches = [idx for idx in df.index if term.lower() in str(idx).lower()]
            if matches:
                # Get the first matching row
                row_idx = matches[0]
                
                # Try to get the value from the specified year column
                if year_column in df.columns and pd.notna(df.loc[row_idx, year_column]):
                    value = safe_float(df.loc[row_idx, year_column])
                    if value is not None:
                        return value
                
                # Try fallback columns if primary column doesn't have a value
                for col in fallback_columns:
                    if col in df.columns and pd.notna(df.loc[row_idx, col]):
                        value = safe_float(df.loc[row_idx, col])
                        if value is not None:
                            return value
        
        return None
    
    # Determine the most recent year column and previous years for comparisons
    year_columns = []
    prev_year_columns = []
    
    if "income_statement" in processed_statements and processed_statements["income_statement"] is not None:
        df = processed_statements["income_statement"]
        # Find columns that look like years (2022, 2023, 2024, etc.)
        year_pattern = re.compile(r'20\d\d')
        year_cols = [col for col in df.columns if isinstance(col, str) and year_pattern.search(str(col))]
        
        if year_cols:
            # Sort in descending order to get most recent years first
            year_cols.sort(reverse=True)
            if len(year_cols) > 0:
                year_columns = [year_cols[0]]
            if len(year_cols) > 1:
                prev_year_columns = year_cols[1:]
    
    # If we didn't find year columns, use the first few columns
    if not year_columns and "income_statement" in processed_statements and processed_statements["income_statement"] is not None:
        cols = processed_statements["income_statement"].columns
        if len(cols) > 0:
            year_columns = [cols[0]]
        if len(cols) > 1:
            prev_year_columns = cols[1:3]  # Use next 2 columns as previous years
    
    # Function to examine raw values in the data to help identify matching rows
    def print_financial_data(statement_type):
        if statement_type in processed_statements and processed_statements[statement_type] is not None:
            df = processed_statements[statement_type]
            print(f"\nExamining {statement_type} for key data:")
            # Print a selection of rows that might contain key metrics
            for idx in df.index:
                idx_str = str(idx).lower()
                if any(term in idx_str for term in [
                    'revenue', 'sales', 'turnover', 'income', 
                    'gross', 'profit', 'ebitda', 'operating', 
                    'research', 'r&d', 'development'
                ]):
                    row_data = df.loc[idx]
                    print(f"  {idx}: {row_data.to_dict()}")
    
    # Print some debugging info to help diagnose issues
    print_financial_data("income_statement")
    
    # Extract total revenue - try multiple approaches
    revenue_value = None
    
    # Approach 1: Try common revenue terms
    if year_columns:
        revenue_value = find_value(
            "income_statement", 
            ["total revenue", "revenue", "net sales", "turnover", "total sales"],
            year_column=year_columns[0],
            fallback_columns=prev_year_columns
        )
    
    # Approach 2: If not found, try to identify the revenue row by size
    # (In income statements, revenue is typically the largest positive value)
    if revenue_value is None and "income_statement" in processed_statements and processed_statements["income_statement"] is not None:
        df = processed_statements["income_statement"]
        if year_columns:
            col = year_columns[0]
            
            # Convert all values to float where possible
            values = []
            for idx in df.index:
                try:
                    val = safe_float(df.loc[idx, col])
                    if val is not None and val > 0:  # Only positive values
                        values.append((idx, val))
                except:
                    pass
            
            # Sort by value (descending)
            values.sort(key=lambda x: x[1], reverse=True)
            
            # Take the largest value that's not unreasonably large
            if values:
                top_rows = values[:3]  # Look at top 3 largest values
                print(f"Largest positive values in {col}:")
                for idx, val in top_rows:
                    print(f"  {idx}: {val}")
                
                # Use the largest value that's in top rows and contains 'revenue' or similar terms
                revenue_row = None
                for idx, val in top_rows:
                    idx_str = str(idx).lower()
                    if any(term in idx_str for term in ['revenue', 'sales', 'turnover', 'income']):
                        revenue_row = idx
                        revenue_value = val
                        print(f"Selected revenue row: {idx} with value {val}")
                        break
                
                # If no obvious revenue row, use the largest value
                if revenue_value is None and top_rows:
                    revenue_row = top_rows[0][0]
                    revenue_value = top_rows[0][1]
                    print(f"Using largest value as revenue: {revenue_row} with value {revenue_value}")
    
    # Set the revenue if found
    if revenue_value is not None:
        metrics["revenue"] = str(int(revenue_value))  # Round to integer for cleaner output
    
    # Calculate revenue growth rate if we have multiple years of data and identified revenue
    if revenue_value is not None and "income_statement" in processed_statements and year_columns and prev_year_columns:
        df = processed_statements["income_statement"]
        
        # Try to find the revenue row
        revenue_matches = [idx for idx in df.index if any(term in str(idx).lower() for term in 
                          ["revenue", "total revenue", "net sales", "turnover", "total sales"])]
        
        # If we identified a revenue row and have columns for current and previous year
        if revenue_matches:
            revenue_row = revenue_matches[0]
            current_year = year_columns[0]
            prev_year = prev_year_columns[0]
            
            # Check if both columns exist
            if current_year in df.columns and prev_year in df.columns:
                try:
                    current_revenue = safe_float(df.loc[revenue_row, current_year])
                    prev_revenue = safe_float(df.loc[revenue_row, prev_year])
                    
                    if current_revenue and prev_revenue and prev_revenue > 0:
                        growth_rate = ((current_revenue - prev_revenue) / prev_revenue) * 100
                        # Cap at reasonable values
                        growth_rate = max(min(growth_rate, 100), -100)
                        metrics["growth_rate"] = f"{growth_rate:.1f}"
                except Exception as e:
                    print(f"Error calculating growth rate: {e}")
    
    # Extract gross profit and calculate margin
    if revenue_value is not None and year_columns:
        # First try to find gross profit directly
        gross_profit_value = find_value(
            "income_statement", 
            ["gross profit", "gross margin", "gross income"],
            year_column=year_columns[0],
            fallback_columns=prev_year_columns
        )
        
        # If found, calculate as a percentage of revenue
        if gross_profit_value is not None:
            try:
                gross_margin = (gross_profit_value / revenue_value) * 100
                # Ensure it's a realistic percentage (between 0 and 100)
                if 0 <= gross_margin <= 100:
                    metrics["gross_margin"] = f"{gross_margin:.1f}"
                else:
                    print(f"Unrealistic gross margin calculated: {gross_margin}%. Using revenue: {revenue_value}, gross profit: {gross_profit_value}")
            except Exception as e:
                print(f"Error calculating gross margin: {e}")
    
    # Extract EBITDA and calculate margin
    if revenue_value is not None and year_columns:
        # Try to find EBITDA or operating profit
        ebitda_value = find_value(
            "income_statement", 
            ["ebitda", "earnings before interest", "operating profit", "operating income"],
            year_column=year_columns[0],
            fallback_columns=prev_year_columns
        )
        
        # Calculate EBITDA margin if we found a value
        if ebitda_value is not None:
            try:
                ebitda_margin = (ebitda_value / revenue_value) * 100
                # Ensure it's a realistic percentage (between 0 and 100)
                if 0 <= ebitda_margin <= 100:
                    metrics["ebitda_margin"] = f"{ebitda_margin:.1f}"
                else:
                    print(f"Unrealistic EBITDA margin calculated: {ebitda_margin}%. Using revenue: {revenue_value}, EBITDA: {ebitda_value}")
            except Exception as e:
                print(f"Error calculating EBITDA margin: {e}")
    
    # Extract R&D expenses and calculate as percentage of revenue
    if revenue_value is not None and year_columns:
        rd_value = find_value(
            "income_statement", 
            ["research and development", "r&d", "research & development", "development costs"],
            year_column=year_columns[0],
            fallback_columns=prev_year_columns
        )
        
        # Calculate R&D percentage if found
        if rd_value is not None:
            try:
                # R&D is typically an expense (negative in some statements)
                rd_value = abs(rd_value)  # Use absolute value to handle both formats
                rd_percentage = (rd_value / revenue_value) * 100
                # Ensure it's a realistic percentage (between 0 and 100)
                if 0 <= rd_percentage <= 100:
                    metrics["rd_percentage"] = f"{rd_percentage:.1f}"
                else:
                    print(f"Unrealistic R&D percentage calculated: {rd_percentage}%. Using revenue: {revenue_value}, R&D: {rd_value}")
            except Exception as e:
                print(f"Error calculating R&D percentage: {e}")
    
    # Check the company name directly for common industry indicators
    company_name_lower = company_name.lower()
    
    # Direct company name checking for well-known industries
    if any(term in company_name_lower for term in ["pharma", "drug", "bio", "life sciences", "therapeutics", "medicine"]):
        metrics["industry"] = "Pharmaceutical"
        print(f"Industry detected from company name: Pharmaceutical")
    elif any(term in company_name_lower for term in ["bank", "invest", "capital", "financial", "asset", "fund"]):
        metrics["industry"] = "Financial"
        print(f"Industry detected from company name: Financial")
    elif any(term in company_name_lower for term in ["tech", "soft", "micro", "byte", "data", "digital", "cyber"]):
        metrics["industry"] = "Technology"
        print(f"Industry detected from company name: Technology")
    
    # Stronger R&D weighting for industry classification
    if metrics["rd_percentage"] != "N/A" and metrics["rd_percentage"]:
        try:
            rd_percentage = float(metrics["rd_percentage"])
            if rd_percentage > 15:
                # Companies with very high R&D are typically pharmaceutical or tech
                print(f"High R&D percentage detected: {rd_percentage}%")
                if rd_percentage > 20:
                    print("Very high R&D suggests pharmaceutical industry")
                    metrics["industry"] = "Pharmaceutical"
        except:
            pass
                    
    # If industry is still not determined, proceed with keyword detection
    if metrics["industry"] == "N/A":
        # Try to determine industry based on keywords in the financial statements
        industry_keywords = {
            "pharmaceutical": ["pharmaceutical", "medicine", "drug", "healthcare", "biotech", "pharma", 
                              "medical", "clinical", "therapeutic", "prescription", "patient", "treatment"],
            "technology": ["software", "hardware", "technology", "it services", "cloud", "computing", "tech", 
                          "digital", "internet", "electronic"],
            "financial": ["banking", "insurance", "investment", "financial services", "bank", "credit", 
                         "asset management", "capital", "finance"],
            "retail": ["retail", "consumer goods", "merchandise", "store", "shop", "e-commerce"],
            "manufacturing": ["manufacturing", "industrial", "production", "factory", "assembly"],
            "energy": ["energy", "oil", "gas", "utility", "power", "electricity", "renewable"],
            "telecommunications": ["telecom", "communications", "network", "cellular", "mobile", "broadband"],
            "automotive": ["automotive", "car", "vehicle", "motor", "transport"],
            "healthcare": ["hospital", "clinic", "medical device", "healthcare services", "patient"],
            "consumer goods": ["consumer products", "fmcg", "food", "beverage", "household"]
        }
        
        # Combine all text from financial statements to analyze for industry keywords
        all_statement_text = ""
        for statement_type in processed_statements:
            if processed_statements[statement_type] is not None:
                all_statement_text += " ".join(map(str, processed_statements[statement_type].index)) + " "
                # Also include column headers
                all_statement_text += " ".join(map(str, processed_statements[statement_type].columns)) + " "
        
        all_statement_text = all_statement_text.lower()
        
        # Find the industry with the most keyword matches
        industry_matches = {}
        for industry, keywords in industry_keywords.items():
            count = sum(all_statement_text.count(keyword) for keyword in keywords)
            if count > 0:
                industry_matches[industry] = count
        
        if industry_matches:
            # Get the industry with the most matches
            top_industry = max(industry_matches.items(), key=lambda x: x[1])[0]
            metrics["industry"] = top_industry.capitalize()
            print(f"Detected industry: {top_industry.capitalize()} with {industry_matches[top_industry]} keyword matches")
    
    # Try to infer business model from financial structure
    if metrics["industry"] != "N/A":
        industry = metrics["industry"].lower()
        
        # Set business model based on industry
        if "pharmaceutical" in industry:
            # Check if R&D percentage is available and high (typical for research-based pharma)
            if metrics["rd_percentage"] != "N/A" and float(metrics["rd_percentage"]) > 10:
                metrics["business_model"] = "Research-based pharmaceutical company"
            else:
                metrics["business_model"] = "Pharmaceutical company"
                
        elif "technology" in industry:
            # Check for high gross margins (typical for software companies)
            if metrics["gross_margin"] != "N/A" and float(metrics["gross_margin"]) > 50:
                metrics["business_model"] = "Software/SaaS company"
            else:
                metrics["business_model"] = "Technology company"
                
        elif "financial" in industry:
            metrics["business_model"] = "Financial services company"
            
        elif "retail" in industry:
            # Low margins typical for retail
            if metrics["gross_margin"] != "N/A" and float(metrics["gross_margin"]) < 40:
                metrics["business_model"] = "Mass-market retail company"
            else:
                metrics["business_model"] = "Retail company"
        else:
            # Generic business model based on industry
            metrics["business_model"] = f"{metrics['industry']} company"
    
    # If we couldn't determine the industry, provide a generic business model
    if metrics["business_model"] == "N/A" and metrics["revenue"] != "N/A":
        metrics["business_model"] = "Company"
    
    # Try to infer key products/services from industry
    if metrics["industry"] != "N/A" and metrics["key_products_services"] == "N/A":
        industry = metrics["industry"].lower()
        
        if "pharmaceutical" in industry:
            metrics["key_products_services"] = "Pharmaceutical products and therapeutics"
        elif "technology" in industry:
            metrics["key_products_services"] = "Technology products and services"
        elif "financial" in industry:
            metrics["key_products_services"] = "Financial products and services"
        elif "retail" in industry:
            metrics["key_products_services"] = "Consumer goods and retail products"
        elif "energy" in industry:
            metrics["key_products_services"] = "Energy production and distribution"
        elif "healthcare" in industry:
            metrics["key_products_services"] = "Healthcare services and products"
    
    # Replace any N/A values with empty strings for metrics that should be numeric
    for key in ["revenue", "growth_rate", "gross_margin", "ebitda_margin", "rd_percentage"]:
        if metrics[key] == "N/A":
            metrics[key] = ""
    
    # Format the metrics for the Perplexity API
    formatted_metrics = {
        "company_name": metrics["company_name"],
        "industry": metrics["industry"],
        "business_model": metrics["business_model"],
        "revenue": metrics["revenue"],
        "growth_rate": metrics["growth_rate"],
        "gross_margin": metrics["gross_margin"],
        "ebitda_margin": metrics["ebitda_margin"],
        "rd_percentage": metrics["rd_percentage"],
        "employee_count": metrics["employee_count"],
        "key_products_services": metrics["key_products_services"],
        "financial_unit": metrics["financial_unit"]
    }
    
    # Save metrics to JSON file
    metrics_file = os.path.join(output_dir, f"{company_name.lower().replace(' ', '_')}_financial_metrics.json")
    with open(metrics_file, 'w') as f:
        json.dump(formatted_metrics, f, indent=4)
    
    print(f"Saved key financial metrics to {metrics_file}")
    return metrics_file

def process_uploaded_financials(pdf_path):
    """
    Wrapper function to process a financial report PDF.
    It extracts financial data and saves it in the appropriate folder.
    Returns the path to the metadata file.
    """
    # Extract company name from PDF filename
    pdf_filename = os.path.basename(pdf_path)
    company_name = os.path.splitext(pdf_filename)[0]
    
    # Create output directory for this company
    company_output_dir = os.path.join(FINANCIAL_DATA_DIR, company_name.lower().replace(" ", "_"))
    ensure_directory_exists(company_output_dir)

    print("\n🚀 Starting Azure Document Intelligence processing...")
    
    # Analyze the uploaded PDF
    analysis_result = analyze_document(pdf_path)
    
    metadata_file = None
    metrics_file = None
    
    if analysis_result:
        # Save the raw analysis response
        save_raw_analysis(analysis_result, company_output_dir)
        
        # Extract tables from the analysis result
        tables = extract_tables_from_analysis(analysis_result)
        
        if tables:
            # Identify financial statements
            financial_statements = identify_financial_statements(tables)
            
            # Process and clean financial statements
            processed_statements = process_financial_statements(financial_statements)
            
            # Save as CSV
            csv_files = save_financials_to_csv(
                processed_statements, 
                company_output_dir, 
                prefix=f"{company_name.lower().replace(' ', '_')}_"
            )
            
            # Save as JSON
            json_files = save_financials_to_json(
                processed_statements, 
                company_output_dir, 
                prefix=f"{company_name.lower().replace(' ', '_')}_"
            )
            
            # NEW: Extract and save key financial metrics
            metrics_file = extract_key_financial_metrics(
                processed_statements,
                company_name,
                company_output_dir
            )
            
            # Add the metrics file to the json_files list
            if metrics_file:
                json_files.append({
                    "type": "financial_metrics",
                    "format": "json",
                    "filename": os.path.basename(metrics_file)
                })
            
            # Create metadata JSON
            metadata_file = create_metadata_json(
                csv_files, 
                json_files, 
                company_output_dir, 
                prefix=f"{company_name.lower().replace(' ', '_')}_"
            )
            
            print(f"\n✅ Financial data extracted and saved in: {company_output_dir}")
            print(f"📄 Metadata file created: {metadata_file}")
        else:
            print("❌ No tables detected in the document analysis.")
    else:
        print("❌ Azure Document Intelligence failed to process the document.")
    
    # Return both the metadata file and metrics file
    return metadata_file, metrics_file

# And update the main function if you're using this script directly:
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
            
            # NEW: Extract and save key financial metrics
            metrics_file = extract_key_financial_metrics(
                processed_statements,
                "AstraZeneca",
                OUTPUT_DIR
            )
            
            # Add the metrics file to the json_files list
            if metrics_file:
                json_files.append({
                    "type": "financial_metrics",
                    "format": "json",
                    "filename": os.path.basename(metrics_file)
                })
            
            # Create metadata JSON
            metadata_file = create_metadata_json(csv_files, json_files, OUTPUT_DIR)
            
            print(f"\n✅ Complete! Financial data has been extracted and saved to CSV and JSON files in: {OUTPUT_DIR}")
            print(f"📄 Metadata file with all information: {metadata_file}")
            print(f"📊 Financial metrics for competitor analysis: {metrics_file}")
        else:
            print("❌ No tables found in the document analysis")
    else:
        print("❌ Document analysis failed")