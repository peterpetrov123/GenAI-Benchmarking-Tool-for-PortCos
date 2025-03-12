import os
import glob
import logging
from azure.storage.blob import BlobServiceClient
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Azure Blob Storage credentials from .env file
AZURE_STORAGE_SAS_URL = os.getenv("AZURE_STORAGE_SAS_URL")
AZURE_STORAGE_SAS_TOKEN = os.getenv("AZURE_STORAGE_SAS_TOKEN")
AZURE_CONTAINER_NAME = os.getenv("AZURE_CONTAINER_NAME")

# Absolute path to financial data folder
FINANCIAL_DATA_DIR = r"C:\Users\peter\Downloads\FYP - AnM GenAI Benchmaking tool\GenAI-Benchmarking-Tool-for-PortCos\financial_data"

def get_blob_service_client():
    """
    Initialize BlobServiceClient using SAS URL.
    """
    if not AZURE_STORAGE_SAS_URL or not AZURE_STORAGE_SAS_TOKEN:
        raise ValueError("Missing Azure Blob Storage credentials in .env file.")

    return BlobServiceClient(account_url=AZURE_STORAGE_SAS_URL, credential=AZURE_STORAGE_SAS_TOKEN)

def upload_file_to_blob(blob_service_client, file_path, blob_path):
    """
    Uploads a single file to Azure Blob Storage.
    """
    try:
        container_client = blob_service_client.get_container_client(AZURE_CONTAINER_NAME)

        # Open and upload the file
        with open(file_path, "rb") as file_data:
            blob_client = container_client.get_blob_client(blob_path)
            blob_client.upload_blob(file_data, overwrite=True)
        
        logging.info(f"✅ Uploaded: {blob_path}")
    except Exception as e:
        logging.error(f"❌ Failed to upload {file_path}: {e}")

def upload_financial_data():
    """
    Scans the financial_data directory and uploads all CSV and JSON files.
    """
    logging.info("🚀 Starting upload process for financial data...")

    blob_service_client = get_blob_service_client()

    # Walk through financial_data directory
    for company in os.listdir(FINANCIAL_DATA_DIR):
        company_path = os.path.join(FINANCIAL_DATA_DIR, company)

        if os.path.isdir(company_path):  # Ensure it's a directory
            logging.info(f"📂 Processing company: {company}")

            # Upload all CSV and JSON files
            for file_path in glob.glob(f"{company_path}\\*.csv") + glob.glob(f"{company_path}\\*.json"):
                file_name = os.path.basename(file_path)
                blob_path = f"{company}/{file_name}"  # Blob path in container
                upload_file_to_blob(blob_service_client, file_path, blob_path)

    logging.info("✅ All financial data uploaded successfully.")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    upload_financial_data()
