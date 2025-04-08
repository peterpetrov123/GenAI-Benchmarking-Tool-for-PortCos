import os
import json
import pandas as pd
import numpy as np
import argparse
from datetime import datetime
from pathlib import Path

# Set up argument parsing
parser = argparse.ArgumentParser(description='Clean and combine financial data')
parser.add_argument('--metrics', help='Path to the financial metrics JSON file')
parser.add_argument('--competitors', help='Path to the competitors JSON file')
parser.add_argument('--financials', help='Path to the competitor financials JSON file')
parser.add_argument('--output-dir', help='Custom output directory for results')
args = parser.parse_args()

# Define standard metrics to extract and standardize
STANDARD_METRICS = [
    {"name": "Annual Revenue", "keys": ["annual_revenue", "revenue"], "unit": "million USD", "format": "${:.1f}M"},
    {"name": "Revenue Growth", "keys": ["revenue_growth", "growth_rate"], "unit": "%", "format": "{:.1f}%"},
    {"name": "Gross Margin", "keys": ["gross_margin"], "unit": "%", "format": "{:.1f}%"},
    {"name": "EBITDA Margin", "keys": ["ebitda_margin"], "unit": "%", "format": "{:.1f}%"},
    {"name": "R&D Percentage", "keys": ["rd_percentage"], "unit": "%", "format": "{:.1f}%"},
    {"name": "Operating Cash Flow", "keys": ["operating_cash_flow", "ocf"], "unit": "million USD", "format": "${:.1f}M"},
    {"name": "Employee Count", "keys": ["employee_count"], "unit": "employees", "format": "{:,}"},
    {"name": "Market Capitalization", "keys": ["market_capitalization", "market_cap"], "unit": "million USD", "format": "${:.1f}M"}
]

def extract_metric_value(data, metric_keys):
    """Extract a metric value from a data dict using a list of possible keys"""
    # For target company, direct access from top level
    if isinstance(data, dict):
        for key in metric_keys:
            if key in data:
                return data[key]
        
        # For competitor metrics, value may be nested
        if "metrics" in data:
            metrics = data["metrics"]
            for key in metric_keys:
                if key in metrics:
                    # Handle both direct values and nested objects
                    if isinstance(metrics[key], dict) and "value" in metrics[key]:
                        return metrics[key]["value"]
                    else:
                        return metrics[key]
    
    return None

def format_metric(value, metric_format):
    """Format a metric value according to its format string"""
    if value is None or pd.isna(value) or value == "N/A":
        return "N/A"
    
    try:
        # Convert string values if needed
        if isinstance(value, str):
            # Remove common formatting and convert to float
            value = value.replace('$', '').replace('%', '').replace('M', '').replace(',', '')
            value = float(value)
        
        return metric_format.format(value)
    except (ValueError, TypeError):
        return str(value)

def clean_and_standardize_data(target_data, competitor_metrics):
    """Standardize and combine metrics from target company and competitors into a dataframe"""
    
    # Extract company name and prepare data structure
    target_company = target_data.get("company_name", "Target Company")
    
    # Create DataFrame structure
    metrics_df = pd.DataFrame(columns=["Metric", target_company])
    
    # Add target company metrics
    for metric in STANDARD_METRICS:
        metric_name = metric["name"]
        value = extract_metric_value(target_data, metric["keys"])
        formatted_value = format_metric(value, metric["format"])
        
        metrics_df.loc[len(metrics_df)] = [metric_name, formatted_value]
    
    # Add competitor metrics
    for competitor in competitor_metrics:
        comp_name = competitor.get("name", "Unknown")
        
        # Add this competitor as a column
        if comp_name not in metrics_df.columns:
            metrics_df[comp_name] = "N/A"
        
        # Fill in values for each metric
        for i, metric in enumerate(STANDARD_METRICS):
            value = extract_metric_value(competitor, metric["keys"])
            formatted_value = format_metric(value, metric["format"])
            metrics_df.loc[i, comp_name] = formatted_value
    
    # Set Metric as index for easier manipulation
    metrics_df.set_index("Metric", inplace=True)
    
    return metrics_df

def save_to_multiple_formats(df, output_dir, company_name):
    """Save the standardized data in multiple formats"""
    company_slug = company_name.lower().replace(' ', '_')
    current_date = datetime.now().strftime("%Y%m%d")
    
    # Create paths for different formats
    output_xlsx = os.path.join(output_dir, f"{company_slug}_comparison_{current_date}.xlsx")
    output_csv = os.path.join(output_dir, f"{company_slug}_comparison_{current_date}.csv")
    output_json = os.path.join(output_dir, f"{company_slug}_comparison_{current_date}.json")
    # We'll skip HTML as it requires Jinja2
    
    # Reset index to make Metric a column
    df_for_save = df.reset_index()
    
    # Save in different formats
    df_for_save.to_excel(output_xlsx, index=False)
    df_for_save.to_csv(output_csv, index=False)
    
    # Save as JSON (simple format, not using pandas to_json which may require styling)
    json_data = {}
    for idx, row in df_for_save.iterrows():
        metric = row['Metric']
        json_data[metric] = {}
        for col in df_for_save.columns:
            if col != 'Metric':
                json_data[metric][col] = row[col]
    
    with open(output_json, 'w', encoding='utf-8') as f:
        json.dump(json_data, f, indent=2)
    
    return {
        "xlsx": output_xlsx,
        "csv": output_csv,
        "json": output_json
    }

def main():
    print("\n" + "="*70)
    print(" FINANCIAL DATA CLEANING AND STANDARDIZATION ".center(70, "="))
    print("="*70 + "\n")
    
    # Get file paths from command line arguments or environment variables
    metrics_file = args.metrics or os.environ.get("METRICS_FILE")
    competitors_file = args.competitors or os.environ.get("COMPETITORS_FILE")
    financials_file = args.financials or os.environ.get("FINANCIALS_FILE")
    
    # Interactive mode if files not provided by command line
    if not all([metrics_file, competitors_file, financials_file]):
        print("Some required file paths not provided. Switching to interactive mode.")
        
        # Find data files in competitor_analysis directory
        comp_analysis_dir = "competitor_analysis"
        if os.path.exists(comp_analysis_dir):
            company_folders = [d for d in os.listdir(comp_analysis_dir) 
                              if os.path.isdir(os.path.join(comp_analysis_dir, d))]
            
            if company_folders:
                print(f"Found {len(company_folders)} company folders for analysis:")
                for i, folder in enumerate(company_folders, 1):
                    print(f"  {i}. {folder.replace('_', ' ').title()}")
                
                selection = input(f"\nSelect a company (1-{len(company_folders)}): ")
                try:
                    index = int(selection) - 1
                    if 0 <= index < len(company_folders):
                        selected_folder = company_folders[index]
                        
                        # Look for required files in this folder
                        folder_path = os.path.join(comp_analysis_dir, selected_folder)
                        
                        # For metrics_file, we need to look in financial_data directory
                        fin_data_dir = "financial_data"
                        if os.path.exists(fin_data_dir):
                            company_slug = selected_folder
                            company_fin_dir = os.path.join(fin_data_dir, company_slug)
                            if os.path.exists(company_fin_dir):
                                metrics_candidates = list(Path(company_fin_dir).glob("*_financial_metrics.json"))
                                if metrics_candidates:
                                    metrics_file = str(metrics_candidates[0])
                        
                        # For competitors and financials files
                        competitors_candidates = list(Path(folder_path).glob("*_competitors_*.json"))
                        financials_candidates = list(Path(folder_path).glob("*_competitor_financials_*.json"))
                        
                        if competitors_candidates:
                            competitors_file = str(competitors_candidates[0])
                        if financials_candidates:
                            financials_file = str(financials_candidates[0])
                    else:
                        print("Invalid selection.")
                except (ValueError, IndexError):
                    print("Invalid selection.")
        
        # If files still not found, prompt for direct input
        if not metrics_file:
            metrics_file = input("Enter path to financial metrics file: ")
        if not competitors_file:
            competitors_file = input("Enter path to competitors file: ")
        if not financials_file:
            financials_file = input("Enter path to financials file: ")
    else:
        print(f"Running in automated mode with the following files:")
        print(f"  - Target Company Metrics: {metrics_file}")
        print(f"  - Competitors List: {competitors_file}")
        print(f"  - Competitor Financials: {financials_file}")
    
    # Ensure all required files exist
    if not all([os.path.exists(f) for f in [metrics_file, competitors_file, financials_file]]):
        missing = []
        if not os.path.exists(metrics_file):
            missing.append("Target metrics file")
        if not os.path.exists(competitors_file):
            missing.append("Competitors file")
        if not os.path.exists(financials_file):
            missing.append("Financials file")
        
        print(f"Error: The following required files were not found: {', '.join(missing)}")
        return
    
    # Define output directory
    if args.output_dir:
        output_dir = args.output_dir
    else:
        # Derive output directory from the metrics file
        metrics_dir = os.path.dirname(metrics_file)
        company_name = os.path.basename(metrics_file).split('_financial_metrics')[0]
        company_slug = company_name.lower().replace(' ', '_')
        output_dir = os.path.join("competitor_analysis", company_slug)
    
    os.makedirs(output_dir, exist_ok=True)
    print(f"Results will be saved to: {output_dir}")
    
    # Load target company data
    try:
        with open(metrics_file, 'r', encoding='utf-8') as f:
            target_data = json.load(f)
        company_name = target_data.get('company_name', 'Unknown')
        print(f"Loaded target company data for {company_name}")
    except Exception as e:
        print(f"Error loading target company data: {e}")
        return
    
    # Load competitors data
    try:
        with open(competitors_file, 'r', encoding='utf-8') as f:
            competitors_data = json.load(f)
        competitors = competitors_data.get('competitors', [])
        print(f"Loaded data for {len(competitors)} competitors")
    except Exception as e:
        print(f"Error loading competitors data: {e}")
        return
    
    # Load competitor financials
    try:
        with open(financials_file, 'r', encoding='utf-8') as f:
            financials_data = json.load(f)
        competitor_metrics = financials_data.get('company_metrics', [])
        print(f"Loaded financial metrics for {len(competitor_metrics)} companies")
    except Exception as e:
        print(f"Error loading competitor financials: {e}")
        return
    
    # Clean and standardize data
    print("\nCleaning and standardizing financial data...")
    standardized_df = clean_and_standardize_data(target_data, competitor_metrics)
    
    # Save the standardized data in multiple formats
    print("Saving standardized comparison data...")
    output_files = save_to_multiple_formats(standardized_df, output_dir, company_name)
    
    print("\nData standardization complete!")
    print(f"Saved comparison files:")
    for format, file_path in output_files.items():
        print(f"  - {format.upper()}: {os.path.basename(file_path)}")
    
    return output_files

if __name__ == "__main__":
    main()