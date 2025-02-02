import os
import requests
import pandas as pd
from bs4 import BeautifulSoup
from azure.storage.blob import BlobServiceClient  # Added import for Blob Storage

def test_azure_document_intelligence():
    endpoint = os.getenv("AZURE_DOC_INTELLIGENCE_ENDPOINT")
    api_key = os.getenv("AZURE_DOC_INTELLIGENCE_API_KEY")
    if not endpoint or not api_key:
        print("Azure Document Intelligence configuration missing!")
        return

    # Example: Prepare headers for API call.
    headers = {"Ocp-Apim-Subscription-Key": api_key}
    # Replace <your-model-path> with the actual endpoint path.
    sample_url = f"{endpoint}/formrecognizer/v2.1/prebuilt/receipt/analyze"

    print("Testing Azure Document Intelligence API connectivity...")
    # NOTE: For a real test, you would post a document file to the API.
    # For now, we simulate a successful response.
    try:
        # response = requests.post(sample_url, headers=headers, files={"file": open("sample.pdf", "rb")})
        # For demo, we simulate a successful response.
        print("Simulated response: { 'status': 'success', 'message': 'API reachable' }")
    except Exception as e:
        print("Error testing Azure API:", e)

def test_web_scraping():
    # Simulate a web scraping task using BeautifulSoup.
    sample_html = """
    <html>
      <head><title>Test Page</title></head>
      <body>
        <div class="financial">Revenue: $1000</div>
      </body>
    </html>
    """
    soup = BeautifulSoup(sample_html, "html.parser")
    revenue_div = soup.find("div", class_="financial")
    if revenue_div:
        print("Web scraping test successful:", revenue_div.text)
    else:
        print("Web scraping test failed.")

def test_blob_storage():
    # Retrieve the Blob Storage SAS URL and token from environment variables.
    sas_url = os.getenv("AZURE_STORAGE_SAS_URL")
    sas_token = os.getenv("AZURE_STORAGE_SAS_TOKEN")
    if not sas_url or not sas_token:
        print("Blob Storage configuration missing!")
        return

    try:
        # Create the BlobServiceClient using the SAS URL and token.
        blob_service_client = BlobServiceClient(account_url=sas_url, credential=sas_token)
        print("Testing Blob Storage connectivity...")

        # Optionally list all containers to verify the connection.
        containers = blob_service_client.list_containers()
        print("Listing Blob Storage containers:")
        for container in containers:
            print(" -", container['name'])
    except Exception as e:
        print("Error connecting to Blob Storage:", e)

def main():
    print("Starting ETL pipeline tests...\n")
    test_azure_document_intelligence()
    print("\n")
    test_web_scraping()
    print("\n")
    test_blob_storage()
    print("\nETL pipeline basic test complete.")

if __name__ == "__main__":
    main()
