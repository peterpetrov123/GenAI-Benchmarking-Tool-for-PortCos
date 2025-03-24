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
import time
from tqdm import tqdm  # For progress bar, install with pip if needed

# Set the output directory to be in the processed folder
OUTPUT_DIR = os.path.join("financial_data", "processed", "european_stocks_financial_data")

def ensure_directory_exists(directory):
    """Make sure the output directory exists"""
    if not os.path.exists(directory):
        print(f"Creating directory: {directory}")
        os.makedirs(directory)
    print(f"Files will be saved to: {directory}")

def load_european_stocks_csv(file_path):
    """
    Load the European stocks CSV file
    
    Args:
        file_path (str): Path to the CSV file
        
    Returns:
        pandas.DataFrame: DataFrame containing the stocks data
    """
    try:
        df = pd.read_csv(file_path)
        print(f"Loaded {len(df)} stocks from {file_path}")
        return df
    except Exception as e:
        print(f"Error loading CSV file: {str(e)}")
        return None

def get_company_financials(ticker, company_name=None):
    """
    Retrieve a company's financial data using the yfinance library.
    
    Args:
        ticker (str): The ticker symbol of the company
        company_name (str, optional): The name of the company
        
    Returns:
        dict: Financial statement dataframes
    """
    # Use the provided company name or default to the ticker if none provided
    company_name = company_name or ticker
    
    try:
        # Create a Ticker object for the company
        ticker_obj = yf.Ticker(ticker)
        
        # Get key financial metrics
        info = ticker_obj.info
        
        # Get financial ratios and metrics
        financial_data = {
            'symbol': ticker,
            'name': company_name,
            'sector': info.get('sector', 'N/A'),
            'industry': info.get('industry', 'N/A'),
            'market_cap': info.get('marketCap', None),
            'pe_ratio': info.get('trailingPE', None),
            'forward_pe': info.get('forwardPE', None),
            'price_to_book': info.get('priceToBook', None),
            'dividend_yield': info.get('dividendYield', None) * 100 if info.get('dividendYield') else None,
            'eps_ttm': info.get('trailingEps', None),
            'eps_forward': info.get('forwardEps', None),
            'profit_margin': info.get('profitMargins', None) * 100 if info.get('profitMargins') else None,
            'roa': info.get('returnOnAssets', None) * 100 if info.get('returnOnAssets') else None,
            'roe': info.get('returnOnEquity', None) * 100 if info.get('returnOnEquity') else None,
            'revenue_ttm': info.get('totalRevenue', None),
            'revenue_per_share': info.get('revenuePerShare', None),
            'price_to_sales': info.get('priceToSalesTrailing12Months', None),
            'ebitda': info.get('ebitda', None),
            'debt_to_equity': info.get('debtToEquity', None),
            'current_ratio': info.get('currentRatio', None),
            'beta': info.get('beta', None),
            'peg_ratio': info.get('pegRatio', None),
            'data_retrieval_date': datetime.now().strftime("%Y-%m-%d")
        }
        
        # Add currency information
        financial_data['currency'] = info.get('currency', 'N/A')
        
        return financial_data
        
    except Exception as e:
        print(f"Error retrieving financial data for {company_name} ({ticker}): {str(e)}")
        return None

def process_companies(stocks_df, num_companies=100):
    """
    Process a specified number of companies from the stocks DataFrame
    
    Args:
        stocks_df (pandas.DataFrame): DataFrame containing stocks data
        num_companies (int): Number of companies to process
        
    Returns:
        pandas.DataFrame: DataFrame with financial data for the processed companies
    """
    # Take the first num_companies stocks
    companies_to_process = stocks_df.head(num_companies)
    results = []
    
    print(f"Processing financial data for {num_companies} companies...")
    
    # Loop through each company with a progress bar
    for idx, row in tqdm(companies_to_process.iterrows(), total=len(companies_to_process)):
        symbol = row['symbol']
        name = row['name']
        
        print(f"\nProcessing {idx+1}/{num_companies}: {name} ({symbol})")
        
        # Some European stock symbols need to be adjusted for yfinance
        # Try different formats if needed
        ticker_variants = [
            symbol,  # Original symbol
            f"{symbol}.{'DE' if row['country'] == 'germany' else row['country'][:2].upper()}",  # Symbol.COUNTRY_CODE
            f"{symbol}-{'DE' if row['country'] == 'germany' else row['country'][:2].upper()}"  # Symbol-COUNTRY_CODE
        ]
        
        financial_data = None
        for ticker in ticker_variants:
            try:
                financial_data = get_company_financials(ticker, name)
                if financial_data:
                    # Add country and exchange information from the original dataset
                    financial_data['country'] = row['country']
                    financial_data['exchange'] = row['exchange']
                    financial_data['data_source'] = row['data_source']
                    financial_data['ticker_used'] = ticker  # Store which ticker format worked
                    break
            except Exception as e:
                print(f"  - Failed with ticker {ticker}: {str(e)}")
        
        if financial_data:
            results.append(financial_data)
        else:
            print(f"  - Could not retrieve data for {name} ({symbol})")
        
        # Add a small delay to avoid hitting API rate limits
        time.sleep(1)
    
    # Convert results to DataFrame
    if results:
        return pd.DataFrame(results)
    else:
        return pd.DataFrame()

def save_to_csv(df, output_dir, filename="european_stocks_financial_data.csv"):
    """
    Save the DataFrame to a CSV file
    
    Args:
        df (pandas.DataFrame): DataFrame to save
        output_dir (str): Output directory path
        filename (str): Output filename
    """
    output_path = os.path.join(output_dir, filename)
    df.to_csv(output_path, index=False)
    print(f"Saved financial data to {output_path}")
    return output_path

def create_metadata_json(input_file, output_file, processed_count, total_count, output_dir):
    """
    Create a metadata JSON file with information about the processing
    """
    metadata = {
        "input_file": input_file,
        "output_file": output_file,
        "companies_processed": processed_count,
        "total_companies_in_source": total_count,
        "processing_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "yfinance_version": yf.__version__
    }
    
    filename = os.path.join(output_dir, "metadata.json")
    with open(filename, 'w') as f:
        json.dump(metadata, f, indent=4)
    print(f"Saved metadata to {filename}")
    return filename

def get_absolute_path(relative_path):
    """
    Get the absolute path from a path relative to the project root
    """
    # Get the current file's directory
    current_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Navigate to project root (assuming this script is in the src directory)
    project_root = os.path.dirname(current_dir)
    
    # Return the absolute path
    return os.path.join(project_root, relative_path)

if __name__ == "__main__":
    # Ensure the output directory exists (with absolute path)
    output_dir_abs = get_absolute_path(OUTPUT_DIR)
    ensure_directory_exists(output_dir_abs)
    
    # Load the European stocks CSV file - use the correct path based on project structure
    csv_file_path = get_absolute_path(os.path.join("financial_data", "processed", "investpy_european_stocks.csv"))
    stocks_df = load_european_stocks_csv(csv_file_path)
    
    if stocks_df is not None and not stocks_df.empty:
        # Number of companies to process
        num_companies = 100
        
        # Process the companies
        financial_data = process_companies(stocks_df, num_companies)
        
        if not financial_data.empty:
            # Save the financial data to CSV
            output_file = save_to_csv(financial_data, output_dir_abs)
            
            # Create metadata JSON
            metadata_file = create_metadata_json(
                csv_file_path, 
                output_file, 
                len(financial_data), 
                len(stocks_df),
                output_dir_abs
            )
            
            # Print summary
            print("\n=== Processing Summary ===")
            print(f"Total companies in source file: {len(stocks_df)}")
            print(f"Companies processed: {len(financial_data)}")
            print(f"Success rate: {len(financial_data)/num_companies*100:.2f}%")
            
            # Show a sample of the data
            print("\n=== Sample of Financial Data ===")
            print(financial_data[['symbol', 'name', 'sector', 'market_cap', 'pe_ratio', 'dividend_yield']].head())
            
            print(f"\nComplete! Financial data for {len(financial_data)} companies has been retrieved and saved to {output_file}")
            print(f"Metadata file: {metadata_file}")
        else:
            print("No financial data was retrieved. Check for errors above.")
    else:
        print(f"Could not load or process the CSV file: {csv_file_path}")