import datetime
import logging
import os
import sys
import json
from azure_processing import process_uploaded_financials
from web_scraper import get_company_financials  # Assuming you'll update web_scraper.py as suggested
from competitor_finder import find_similar_companies
from blob_storage import upload_financial_data

# Configure Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Paths
FINANCIAL_DATA_DIR = r"C:\Users\peter\Downloads\FYP - AnM GenAI Benchmaking tool\GenAI-Benchmarking-Tool-for-PortCos\financial_data"
PDF_UPLOAD_DIR = r"C:\Users\peter\Downloads\FYP - AnM GenAI Benchmaking tool\GenAI-Benchmarking-Tool-for-PortCos\test_data"
PROCESSED_DIR = os.path.join(FINANCIAL_DATA_DIR, "processed")

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
    processed_data_path = process_uploaded_financials(pdf_path)
    
    # If process_uploaded_financials doesn't return a path, we need to construct it
    if not processed_data_path:
        # Construct a path where the processed data should be
        company_dir = os.path.join(FINANCIAL_DATA_DIR, company_name.lower().replace(" ", "_"))
        processed_data_path = os.path.join(company_dir, f"{company_name.lower().replace(' ', '_')}_metadata.json")
    
    logging.info("✅ PDF processed successfully.")
    return processed_data_path, company_name

def identify_competitors(processed_data_path, company_name):
    """
    Step 2: Use CompetitorFinder to identify similar companies.
    """
    logging.info("🔍 Identifying competitor companies...")
    
    # Create directory for competitors data
    competitors_dir = os.path.join(FINANCIAL_DATA_DIR, "competitors")
    os.makedirs(competitors_dir, exist_ok=True)
    
    # Find similar companies
    similar_companies = find_similar_companies(processed_data_path, max_companies=5)
    
    # Save competitors to JSON
    competitors_file = os.path.join(competitors_dir, f"{company_name.lower().replace(' ', '_')}_competitors.json")
    with open(competitors_file, 'w') as f:
        json.dump(similar_companies, f, indent=4)
    
    logging.info(f"✅ Found {len(similar_companies)} similar companies.")
    return similar_companies

def scrape_competitor_data(similar_companies):
    """
    Step 3: Scrape financial data for the identified competitors.
    """
    logging.info("🔍 Scraping competitor financial data...")
    
    scraped_companies = []
    
    # Update your web_scraper.py to include a function like get_company_financials(ticker, company_name)
    for company in similar_companies:
        company_symbol = company.get('symbol')
        company_name = company.get('name')
        
        if not company_symbol:
            logging.warning(f"⚠️ No ticker symbol for {company_name}, skipping...")
            continue
        
        logging.info(f"🔍 Scraping financial data for {company_name} ({company_symbol})...")
        
        # Create directory for this company
        company_dir = os.path.join(FINANCIAL_DATA_DIR, company_symbol.lower())
        os.makedirs(company_dir, exist_ok=True)
        
        # Get company financials
        try:
            financials = get_company_financials(company_symbol, company_name)
            
            if financials:
                # Save financials to CSV and JSON
                for name, df in financials.items():
                    if df is not None and not df.empty:
                        # Save as CSV
                        csv_path = os.path.join(company_dir, f"{company_symbol.lower()}_{name}.csv")
                        df.to_csv(csv_path)
                        
                        # Save as JSON
                        json_path = os.path.join(company_dir, f"{company_symbol.lower()}_{name}.json")
                        try:
                            json_data = json.loads(df.reset_index().to_json(orient='records'))
                            with open(json_path, 'w') as f:
                                json.dump(json_data, f, indent=4)
                        except Exception as e:
                            logging.error(f"Error converting DataFrame to JSON: {str(e)}")
                            # Alternative method
                            df.reset_index().to_json(json_path, orient='records', indent=4)
                
                # Create metadata for this company
                metadata = {
                    "company": company_name,
                    "ticker": company_symbol,
                    "retrieval_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "source": "Yahoo Finance via yfinance"
                }
                
                metadata_path = os.path.join(company_dir, f"{company_symbol.lower()}_metadata.json")
                with open(metadata_path, 'w') as f:
                    json.dump(metadata, f, indent=4)
                
                logging.info(f"✅ Saved financial data for {company_name}")
                scraped_companies.append(company_symbol)
            else:
                logging.warning(f"⚠️ No financial data retrieved for {company_name}")
                
        except Exception as e:
            logging.error(f"❌ Error scraping data for {company_name}: {str(e)}")
    
    logging.info(f"✅ Scraped data for {len(scraped_companies)} companies")
    return scraped_companies

def upload_to_blob():
    """
    Step 4: Upload all collected data to Azure Blob Storage.
    """
    logging.info("☁ Uploading financial data to Azure Blob Storage...")
    upload_financial_data()
    logging.info("✅ Upload completed.")

def main():
    """
    Main function: Handles the entire financial data processing pipeline.
    """
    logging.info("🚀 Starting Financial Data Processing Pipeline...")

    # Step 1: Process the uploaded PDF
    processed_data_path, company_name = upload_pdf()

    # Step 2: Identify competitor companies
    similar_companies = identify_competitors(processed_data_path, company_name)

    # Step 3: Scrape financial data for competitors
    scraped_companies = scrape_competitor_data(similar_companies)

    # Step 4: Upload all collected data to Azure Blob Storage
    upload_to_blob()

    logging.info("🏁 Financial Data Pipeline Completed Successfully.")

if __name__ == "__main__":
    main()