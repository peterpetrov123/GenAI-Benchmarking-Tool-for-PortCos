# First try to install yfinance if it's not already installed
try:
    import yfinance as yf
except ImportError:
    print("yfinance not found. Installing...")
    import subprocess
    import sys
    subprocess.check_call([sys.executable, "-m", "pip", "install", "yfinance"])
    print("yfinance installed successfully!")
    import yfinance as yf

import pandas as pd
import json
from datetime import datetime
import os

# Set the output directory
OUTPUT_DIR = r"C:\Users\peter\Downloads\FYP - AnM GenAI Benchmaking tool\GenAI-Benchmarking-Tool-for-PortCos\financial_data\pfizer"

def ensure_directory_exists(directory):
    """Make sure the output directory exists"""
    if not os.path.exists(directory):
        print(f"Creating directory: {directory}")
        os.makedirs(directory)
    print(f"Files will be saved to: {directory}")

def get_pfizer_financials():
    """
    Retrieve Pfizer's financial data using the yfinance library.
    Returns financial statement dataframes.
    """
    print("Retrieving Pfizer financial data using yfinance...")
    
    # Create a Ticker object for Pfizer
    pfizer = yf.Ticker("PFE")
    
    # Get income statement, balance sheet, and cash flow statement
    income_statement = pfizer.income_stmt
    balance_sheet = pfizer.balance_sheet
    cash_flow = pfizer.cashflow
    
    # Convert from annual to quarterly if needed
    try:
        income_statement_quarterly = pfizer.quarterly_income_stmt
        balance_sheet_quarterly = pfizer.quarterly_balance_sheet
        cash_flow_quarterly = pfizer.quarterly_cashflow
    except:
        print("Quarterly data might not be available for all statements")
        income_statement_quarterly = None
        balance_sheet_quarterly = None
        cash_flow_quarterly = None
    
    return {
        'income_statement': income_statement,
        'balance_sheet': balance_sheet,
        'cash_flow': cash_flow,
        'income_statement_quarterly': income_statement_quarterly,
        'balance_sheet_quarterly': balance_sheet_quarterly,
        'cash_flow_quarterly': cash_flow_quarterly
    }

def save_financials_to_csv(financials, output_dir, prefix="pfizer_"):
    """
    Save financial dataframes to CSV files.
    """
    saved_files = []
    for name, df in financials.items():
        if df is not None and not df.empty:
            filename = os.path.join(output_dir, f"{prefix}{name}.csv")
            df.to_csv(filename)
            print(f"Saved {filename}")
            saved_files.append({"type": name, "format": "csv", "filename": filename})
    return saved_files

def save_financials_to_json(financials, output_dir, prefix="pfizer_"):
    """
    Save financial dataframes to JSON files.
    """
    saved_files = []
    for name, df in financials.items():
        if df is not None and not df.empty:
            # Convert DataFrame to JSON-friendly format
            # Handle date formatting for JSON serialization
            json_data = {}
            for column in df.columns:
                col_name = column.strftime('%Y-%m-%d') if isinstance(column, pd.Timestamp) else str(column)
                json_data[col_name] = {}
                for index in df.index:
                    value = df.loc[index, column]
                    # Convert numpy types to native Python types for JSON serialization
                    if hasattr(value, 'item'):
                        value = value.item()
                    # Handle NaN values
                    if pd.isna(value):
                        value = None
                    json_data[col_name][index] = value
            
            filename = os.path.join(output_dir, f"{prefix}{name}.json")
            with open(filename, 'w') as f:
                json.dump(json_data, f, indent=4)
            print(f"Saved {filename}")
            saved_files.append({"type": name, "format": "json", "filename": filename})
    return saved_files

def create_metadata_json(csv_files, json_files, output_dir, prefix="pfizer_"):
    """
    Create a metadata JSON file with information about all saved files
    and the date of retrieval.
    """
    metadata = {
        "company": "Pfizer Inc.",
        "ticker": "PFE",
        "retrieval_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
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

def print_summary(financials):
    """
    Print a summary of the financial data.
    """
    print("\n=== Pfizer Financial Data Summary ===")
    
    # Print summary of annual income statement
    income_stmt = financials['income_statement']
    if income_stmt is not None and not income_stmt.empty:
        print("\nIncome Statement (Annual) - Last 4 Years:")
        # Try to find and display key metrics
        key_metrics = ['Total Revenue', 'Operating Income', 'Net Income']
        available_metrics = [metric for metric in key_metrics if metric in income_stmt.index]
        
        if available_metrics:
            income_summary = income_stmt.loc[available_metrics]
            print(income_summary)
            
            # Calculate net margin if possible
            if 'Total Revenue' in available_metrics and 'Net Income' in available_metrics:
                net_margin = income_stmt.loc['Net Income'] / income_stmt.loc['Total Revenue'] * 100
                print("\nNet Profit Margin (%):")
                print(net_margin)
        else:
            print("Key metrics not found in standard format. Available metrics (first 10):")
            for i, key in enumerate(income_stmt.index[:10]):
                print(f"  {key}")
            print("  ...")
    
    # Print summary of balance sheet
    balance = financials['balance_sheet']
    if balance is not None and not balance.empty:
        print("\nBalance Sheet (Annual) - Key Metrics:")
        key_metrics = ['Total Assets', 'Total Liabilities Net Minority Interest', 'Total Equity Gross Minority Interest']
        available_metrics = [metric for metric in key_metrics if metric in balance.index]
        
        if available_metrics:
            for metric in available_metrics:
                print(f"{metric}:\n{balance.loc[metric]}\n")
        else:
            print("Key metrics not found in standard format. Available metrics (first 10):")
            for i, key in enumerate(balance.index[:10]):
                print(f"  {key}")
            print("  ...")

if __name__ == "__main__":
    # Ensure the output directory exists
    ensure_directory_exists(OUTPUT_DIR)
    
    # Get financial data
    financials = get_pfizer_financials()
    
    # Save to CSV files
    csv_files = save_financials_to_csv(financials, OUTPUT_DIR)
    
    # Save to JSON files
    json_files = save_financials_to_json(financials, OUTPUT_DIR)
    
    # Create metadata JSON with file info and retrieval date
    metadata_file = create_metadata_json(csv_files, json_files, OUTPUT_DIR)
    
    # Print summary
    print_summary(financials)
    
    print(f"\nComplete! Financial data has been retrieved and saved to CSV and JSON files in: {OUTPUT_DIR}")
    print(f"Metadata file with all information: {metadata_file}")