"""
ETL Pipeline for Financial Data Extraction

Modules:
- azure_processing.py : Handles Azure Document Intelligence API calls.
- blob_storage.py     : Uploads PDFs to Azure Blob Storage.
- web_scraper.py      : Scrapes competitor financial data from Pfizer.
- db_handler.py       : Saves extracted financials to PostgreSQL.

"""

# Import commonly used functions for easier access when importing src package
from .azure_processing import process_financial_report
from .blob_storage import store_pdf_in_blob_storage
from .web_scraper import scrape_competitor_data
from .db_handler import save_financial_data
