import os
import re
import time
import requests
from bs4 import BeautifulSoup
from azure.storage.blob import BlobServiceClient

def extract_kpis_from_pdf_result(analysis_result):
    """
    Simulate extraction of KPIs from the Azure Document Intelligence JSON result.
    Expected structure (for demo purposes):
    {
       "documentResults": [
           {
              "fields": {
                  "Revenue": {"value": "$1B"},
                  "ProfitMargin": {"value": "10%"},
                  "R&D": {"value": "$200M"}
              }
           }
       ]
    }
    """
    try:
        doc_result = analysis_result.get("documentResults", [{}])[0]
        fields = doc_result.get("fields", {})
        kpis = {
            "Revenue": fields.get("Revenue", {}).get("value", "N/A"),
            "Profit Margin": fields.get("ProfitMargin", {}).get("value", "N/A"),
            "R&D Spending": fields.get("R&D", {}).get("value", "N/A")
        }
        return kpis
    except Exception as e:
        print("Error extracting KPIs from PDF result:", e)
        return {}

def extract_kpis_from_web(soup):
    """
    Extracts financial KPIs from the competitor website content.
    This demo looks for patterns like "Revenue: $XXX", "Profit:" and "R&D:".
    """
    text = soup.get_text(separator=" ")
    revenue = re.search(r"Revenue:\s*\$([\d,\.]+)", text)
    profit = re.search(r"Profit(?: Margin)?:\s*([\d,\.%]+)", text)
    rnd = re.search(r"R&D(?: Spending)?:\s*\$([\d,\.]+)", text)
    kpis = {
        "Revenue": f"${revenue.group(1)}" if revenue else "N/A",
        "Profit": profit.group(1) if profit else "N/A",
        "R&D Spending": f"${rnd.group(1)}" if rnd else "N/A"
    }
    return kpis

def store_pdf_in_blob_storage(file_path):
    """
    Uploads the given PDF file to Azure Blob Storage.
    Requires environment variables:
    - AZURE_STORAGE_SAS_URL
    - AZURE_STORAGE_SAS_TOKEN
    - Optionally, AZURE_STORAGE_CONTAINER_NAME (default: 'financial-reports')
    """
    sas_url = os.getenv("AZURE_STORAGE_SAS_URL")
    sas_token = os.getenv("AZURE_STORAGE_SAS_TOKEN")
    container_name = os.getenv("AZURE_STORAGE_CONTAINER_NAME", "financial-reports")
    if not sas_url or not sas_token:
        print("Blob Storage configuration missing!")
        return
    
    try:
        blob_service_client = BlobServiceClient(account_url=sas_url, credential=sas_token)
        # Directly get the blob client for the target container and blob.
        blob_client = blob_service_client.get_blob_client(container=container_name, blob=os.path.basename(file_path))
        with open(file_path, "rb") as data:
            blob_client.upload_blob(data, overwrite=True)
        print(f"Successfully uploaded '{file_path}' to Blob Storage container '{container_name}'.")
    except Exception as e:
        print("Error uploading PDF to Blob Storage:", e)

def test_azure_document_intelligence():
    endpoint = os.getenv("AZURE_DOC_INTELLIGENCE_ENDPOINT")
    api_key = os.getenv("AZURE_DOC_INTELLIGENCE_API_KEY")
    if not endpoint or not api_key:
        print("Azure Document Intelligence configuration missing!")
        return None

    file_path = "AstraZeneca_AR_2023.pdf"
    if not os.path.exists(file_path):
        print(f"File '{file_path}' not found!")
        return None

    headers = {
        "Ocp-Apim-Subscription-Key": api_key,
        "Content-Type": "application/pdf"
    }
    url = f"{endpoint}/formrecognizer/documentModels/prebuilt-document:analyze?api-version=2022-08-31"
    
    print("Testing Azure Document Intelligence API with actual PDF...")
    try:
        with open(file_path, "rb") as f:
            file_data = f.read()
        response = requests.post(url, headers=headers, data=file_data)
        
        if response.status_code != 202:
            print("Error: Received status code", response.status_code)
            print("Response:", response.text)
            return None
        
        operation_url = response.headers.get("Operation-Location")
        if not operation_url:
            print("Error: Operation-Location header missing in response")
            return None
        
        analysis_result = None
        for _ in range(10):
            time.sleep(2)
            result_response = requests.get(operation_url, headers={"Ocp-Apim-Subscription-Key": api_key})
            if result_response.status_code != 200:
                print("Error fetching analysis result:", result_response.text)
                return None
            result_json = result_response.json()
            status = result_json.get("status")
            if status == "succeeded":
                analysis_result = result_json
                break
            elif status == "failed":
                print("Analysis failed:", result_json)
                return None
            else:
                print("Analysis in progress...")
        
        if analysis_result:
            kpis = extract_kpis_from_pdf_result(analysis_result)
            print("\nExtracted PDF Report KPIs:")
            for key, value in kpis.items():
                print(f" - {key}: {value}")
            return file_path
        else:
            print("Analysis did not complete in the expected time.")
            return None
    except Exception as e:
        print("Error during Azure Document Intelligence API call:", e)
        return None

def test_web_scraping():
    url = "https://www.pfizer.com/sites/default/files/investors/financial_reports/annual_reports/2023/"
    print("\nTesting web scraping on competitor website:", url)
    try:
        response = requests.get(url)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, "html.parser")
        
        pdf_links = [a['href'] for a in soup.find_all("a", href=True) if ".pdf" in a['href'].lower()]
        if pdf_links:
            print("\nFound the following PDF links for competitor financial reports:")
            for link in pdf_links:
                print(" -", link)
        else:
            print("No PDF links found on the competitor page.")
        
        kpis = extract_kpis_from_web(soup)
        print("\nExtracted Competitor Website KPIs:")
        for key, value in kpis.items():
            print(f" - {key}: {value}")
    except Exception as e:
        print("Error scraping competitor website:", e)

def main():
    print("Starting ETL pipeline tests...\n")
    
    # Process the PDF with Azure Document Intelligence and extract KPIs.
    pdf_file = test_azure_document_intelligence()
    
    # Upload the PDF report to Blob Storage if processing succeeded.
    if pdf_file:
        store_pdf_in_blob_storage(pdf_file)
    
    # Scrape the competitor website and extract KPIs.
    test_web_scraping()
    
    print("\nETL pipeline test complete.")

if __name__ == "__main__":
    main()
