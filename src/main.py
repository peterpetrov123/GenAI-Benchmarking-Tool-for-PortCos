import logging
import os
import sys
from azure_processing import process_uploaded_financials
from web_scraper import get_pfizer_financials  # Modify later for AstraZeneca too
from blob_storage import upload_financial_data

# Configure Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Paths
FINANCIAL_DATA_DIR = r"C:\Users\peter\Downloads\FYP - AnM GenAI Benchmaking tool\GenAI-Benchmarking-Tool-for-PortCos\financial_data"
PDF_UPLOAD_DIR = r"C:\Users\peter\Downloads\FYP - AnM GenAI Benchmaking tool\GenAI-Benchmarking-Tool-for-PortCos\test_data"

def upload_pdf():
    """
    Step 1: User provides a PDF, and it's processed using Azure Document Intelligence.
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
    logging.info(f"📂 Selected PDF: {selected_pdf}")

    # Process the PDF with Azure Document Intelligence
    process_uploaded_financials(pdf_path)
    logging.info("✅ PDF processed successfully.")

def scrape_competitor_data():
    """
    Step 2: Scrape Pfizer & AstraZeneca financial data from Yahoo Finance.
    """
    logging.info("🔍 Scraping competitor financial data...")

    # Scrape Pfizer financials
    pfizer_data = get_pfizer_financials()
    if pfizer_data:
        for name, df in pfizer_data.items():
            if df is not None and not df.empty:
                file_path_csv = os.path.join(FINANCIAL_DATA_DIR, "pfizer", f"pfizer_{name}.csv")
                file_path_json = os.path.join(FINANCIAL_DATA_DIR, "pfizer", f"pfizer_{name}.json")
                df.to_csv(file_path_csv)
                df.to_json(file_path_json)
                logging.info(f"✅ Pfizer {name} saved.")

    # (Later: Add AstraZeneca scraping using get_astrazeneca_financials())
    logging.info("✅ Scraping completed.")

def upload_to_blob():
    """
    Step 3: Upload extracted and scraped financial data to Azure Blob Storage.
    """
    logging.info("☁ Uploading financial data to Azure Blob Storage...")
    upload_financial_data()
    logging.info("✅ Upload completed.")

def main():
    """
    Main function: Handles user input, PDF processing, scraping, and Azure upload.
    """
    logging.info("🚀 Starting Financial Data Processing Pipeline...")

    # Step 1: User uploads a PDF financial report
    upload_pdf()

    # Step 2: Scrape competitor financial data
    scrape_competitor_data()

    # Step 3: Upload all collected data to Azure Blob Storage
    upload_to_blob()

    logging.info("🏁 Financial Data Pipeline Completed Successfully.")

if __name__ == "__main__":
    main()
