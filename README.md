# GenAI Benchmarking Tool for PortCos

## Overview

The **GenAI Benchmarking Tool for PortCos** is designed to ingest, transform, and analyze financial data from various sources (e.g., PortCo financial reports and competitor data) using advanced machine learning and data processing techniques. This project leverages Azure services, PostgreSQL, and containerization with Docker to create an end-to-end pipeline.

## Project Roadmap

The project is divided into the following phases:

1. **Phase 1: Project Setup (31st January – 16th February 2025)**
   - **Objective:** Set up the environment, tools, and foundational workflows.
   - **Key Tasks:**
     - Configure access to Azure Document Intelligence, PostgreSQL, and Blob Storage.
     - Set up a containerized working environment using Docker.
     - Install and test required Python libraries (Pandas, NumPy, OpenPyXL, PyPDF2, BeautifulSoup, Selenium, etc.).
     - Validate connectivity to external APIs and services.
     - **Deliverable:** A fully operational data ingestion and storage framework with successful connectivity tests and supervisor approval.

2. **Phase 2: Data Ingestion and Transformation (17th February – 6th March 2025)**
   - **Objective:** Build and refine the ETL pipeline for data collection, cleaning, and storage.
   - **Key Tasks:**
     - Extract PortCo financial data using Azure Document Intelligence.
     - Scrape competitor financial data using BeautifulSoup/Selenium and external APIs.
     - Normalize and transform data using Pandas.
     - Store cleaned data in PostgreSQL and use Blob Storage for unstructured files.
     - **Deliverable:** A fully functional ETL pipeline with cleaned data ready for analysis.

3. **Phase 3: Machine Learning Models (7th March – 24th March 2025)**
   - Develop and deploy ML models for time-series forecasting, anomaly detection, and clustering.

4. **Phase 4: Dashboard and Reporting (25th March – 11th April 2025)**
   - Build interactive dashboards using PowerBI and automate financial reporting.

5. **Phase 5: Finalization and Submission (12th April – 25th April 2025)**
   - Final refinements, documentation, and project submission.

## Phase 1: Environment Setup and Testing

### Environment Setup

- **Development Tools:**
  - **VSCode:** For code development.
  - **Docker & Docker Compose:** For containerizing and running the application and its dependencies.
  - **Python 3.9:** Used as the base image in Docker.

- **Services Configured:**
  - **Azure Document Intelligence:** For parsing financial reports.
  - **PostgreSQL:** For structured data storage.
  - **Azure Blob Storage (via Azurite):** For storing large unstructured files (e.g., PDFs).

- **Python Libraries Installed:**
  - `pandas`, `numpy`, `openpyxl`, `PyPDF2`, `beautifulsoup4`, `selenium`, `requests`, `azure-storage-blob`, etc.

### Docker Configuration

- **Dockerfile:**  
  Builds the image from `python:3.9-slim`, installs dependencies, and sets the default command to run `main.py`.

- **docker-compose.yml:**  
  Orchestrates the following containers:
  - **app:** Runs the Python application.
  - **postgres:** Runs the PostgreSQL database.
  - **azurite:** Emulates Azure Blob Storage.

### Environment Variables

- **The `.env` file contains critical configuration details (ensure this file is added to the `.gitignore`):**

    ```dotenv
    # Azure Document Intelligence configuration
    AZURE_DOC_INTELLIGENCE_ENDPOINT=******
    AZURE_DOC_INTELLIGENCE_API_KEY=your_api_key

    # Azure Blob Storage configuration (using a container-scoped SAS token)
    AZURE_STORAGE_SAS_URL=https://ucldev01.blob.core.windows.net
    AZURE_STORAGE_SAS_TOKEN=******
    AZURE_CONTAINER_NAME=ucl


### How to Run

1. **Clone the repository:**
   ```bash
   git clone https://github.com/peterpetrov123/GenAI-Benchmarking-Tool-for-PortCos
   cd GenAI-Benchmarking-Tool-for-PortCos

2. **Ensure the `.env` file is configured (and added to the .gitignore file).**

3. **Build and run the containers with:**
    ```bash
    docker-compose up --build

4. **Monitor the logs to see connectivity tests for Azure Document Intelligence, web scraping, and Blob Storage.**