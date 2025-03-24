import os
import json
import csv
import datetime
import pandas as pd
import glob
from pathlib import Path

def load_json_file(file_path):
    """Load data from a JSON file"""
    try:
        with open(file_path, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading {file_path}: {str(e)}")
        return None

def get_latest_file(directory, pattern):
    """Get the most recent file matching the pattern in the directory"""
    files = glob.glob(os.path.join(directory, pattern))
    if not files:
        return None
    return max(files, key=os.path.getmtime)

def convert_to_numeric(value_str):
    """Convert string value to numeric, handling various formats"""
    if not value_str or value_str == "N/A":
        return None
    
    # Remove any currency symbols and commas
    clean_value = str(value_str)
    for char in ['$', '€', '£', ',', ' ']:
        clean_value = clean_value.replace(char, '')
    
    # Handle percentage values
    if '%' in clean_value:
        return float(clean_value.replace('%', ''))
    
    # Handle values with M, B indicators
    if clean_value.endswith('M'):
        return float(clean_value[:-1]) * 1000000
    elif clean_value.endswith('B'):
        return float(clean_value[:-1]) * 1000000000
    
    try:
        return float(clean_value)
    except ValueError:
        return None

def format_metric_value(value, metric_type):
    """Format a metric value consistently across all companies"""
    if value is None:
        return "Missing value"
    
    # Format based on metric type
    if metric_type in ["revenue_growth", "gross_margin", "ebitda_margin", "rd_percentage"]:
        # Percentage values
        return f"{value:.1f}%"
    elif metric_type == "annual_revenue":
        # Revenue in millions
        return f"${value:,.0f}M"
    elif metric_type == "operating_cash_flow":
        # Cash flow in millions
        return f"${value:,.2f}M"
    elif metric_type == "market_capitalization":
        # Market cap in millions
        return f"${value:,.0f}M"
    elif metric_type == "employee_count":
        # Employee count as integer
        try:
            return f"{int(value):,}"
        except (ValueError, TypeError):
            return str(value)
    else:
        # Default formatting
        if isinstance(value, (int, float)):
            return f"{value:,}"
        return str(value)

def get_competitor_metric(competitor, metric_name):
    """Get a specific metric from a competitor's metrics"""
    if "metrics" not in competitor:
        return None
    
    metric = competitor["metrics"].get(metric_name)
    if not metric:
        return None
    
    value = metric.get("value")
    if value is None:
        return None
    
    # Convert to appropriate numeric type if possible
    if isinstance(value, (int, float)):
        return value
    
    try:
        return float(value)
    except (ValueError, TypeError):
        return value

def normalize_input_company_data(company_data):
    """Convert input company data to the same format as competitor data"""
    # Extract basic information
    company_name = company_data.get("company_name", "Input Company")
    
    # Create a structured format matching competitor data
    normalized_data = {
        "name": company_name,
        "ticker": "N/A",  # Private companies typically don't have tickers
        "metrics": {}
    }
    
    # Map input company fields to competitor metric format
    mapping = {
        "revenue": "annual_revenue",
        "growth_rate": "revenue_growth",
        "gross_margin": "gross_margin",
        "ebitda_margin": "ebitda_margin",
        "rd_percentage": "rd_percentage",
        "employee_count": "employee_count"
    }
    
    # Create metrics in the same format as competitor data
    for input_field, metric_name in mapping.items():
        value = company_data.get(input_field)
        if value not in (None, "N/A", ""):
            try:
                # Ensure value is numeric
                numeric_value = float(value)
                normalized_data["metrics"][metric_name] = {
                    "value": numeric_value,
                    "unit": "%" if input_field in ("growth_rate", "gross_margin", "ebitda_margin", "rd_percentage") else "",
                    "period": "Latest available",
                    "source": "Company data"
                }
            except (ValueError, TypeError):
                pass
    
    return normalized_data

def combine_company_data(input_company_path, competitors_path):
    """Combine input company and competitor data"""
    # Load the input company data
    input_company_data = load_json_file(input_company_path)
    if not input_company_data:
        print(f"Failed to load input company data from {input_company_path}")
        return None
    
    # Load the competitor financial data
    competitors_data = load_json_file(competitors_path)
    if not competitors_data or "company_metrics" not in competitors_data:
        print(f"Failed to load competitor data from {competitors_path}")
        return None
    
    # Normalize input company data to match competitor format
    normalized_input_company = normalize_input_company_data(input_company_data)
    
    # Combine the data
    all_companies = [normalized_input_company] + competitors_data["company_metrics"]
    
    return all_companies

def create_comparison_table(all_companies):
    """Create a comparison table from all company data"""
    # Define the metrics to include in the comparison
    metrics = [
        {"id": "annual_revenue", "name": "Annual Revenue"},
        {"id": "revenue_growth", "name": "Revenue Growth"},
        {"id": "gross_margin", "name": "Gross Margin"},
        {"id": "ebitda_margin", "name": "EBITDA Margin"},
        {"id": "rd_percentage", "name": "R&D % of Revenue"},
        {"id": "operating_cash_flow", "name": "Operating Cash Flow"},
        {"id": "employee_count", "name": "Employee Count"},
        {"id": "market_capitalization", "name": "Market Cap"}
    ]
    
    # Add any industry-specific metrics
    # Check if any company has pipeline_products or clinical_trials metrics
    for company in all_companies:
        if company.get("metrics", {}).get("pipeline_products"):
            metrics.append({"id": "pipeline_products", "name": "Pipeline Products"})
            break
    
    for company in all_companies:
        if company.get("metrics", {}).get("clinical_trials"):
            metrics.append({"id": "clinical_trials", "name": "Clinical Trials"})
            break
    
    # Build the comparison table
    table = []
    
    # Header row
    header_row = ["Metric"]
    for company in all_companies:
        header_row.append(company["name"])
    table.append(header_row)
    
    # Data rows
    for metric in metrics:
        row = [metric["name"]]
        for company in all_companies:
            metric_value = get_competitor_metric(company, metric["id"])
            row.append(format_metric_value(metric_value, metric["id"]))
        table.append(row)
    
    return table

def save_comparison_data(input_company_data, comparison_table, output_dir):
    """Save comparison data as CSV and JSON"""
    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)
    
    # Get company name for file naming
    company_name = input_company_data.get("company_name", "company")
    company_slug = company_name.lower().replace(' ', '_')
    current_date = datetime.datetime.now().strftime("%Y%m%d")
    
    # Save as CSV
    csv_filename = os.path.join(output_dir, f"{company_slug}_comparison_{current_date}.csv")
    with open(csv_filename, 'w', newline='') as csvfile:
        writer = csv.writer(csvfile)
        for row in comparison_table:
            writer.writerow(row)
    
    # Save as JSON (same data but in JSON format)
    json_filename = os.path.join(output_dir, f"{company_slug}_comparison_{current_date}.json")
    
    # Convert table to JSON-friendly structure
    json_data = {
        "company_name": company_name,
        "comparison_date": datetime.datetime.now().strftime("%Y-%m-%d"),
        "metrics": []
    }
    
    # Skip the header row
    header = comparison_table[0]
    companies = header[1:]
    
    for i in range(1, len(comparison_table)):
        metric_row = comparison_table[i]
        metric_name = metric_row[0]
        metric_values = metric_row[1:]
        
        metric_data = {
            "metric": metric_name,
            "values": {}
        }
        
        for j, company in enumerate(companies):
            metric_data["values"][company] = metric_values[j]
        
        json_data["metrics"].append(metric_data)
    
    with open(json_filename, 'w') as jsonfile:
        json.dump(json_data, jsonfile, indent=2)
    
    print(f"Saved comparison as CSV: {csv_filename}")
    print(f"Saved comparison as JSON: {json_filename}")
    
    return csv_filename, json_filename

def create_standardized_dataframe(all_companies, metrics_list):
    """Create a standardized DataFrame with consistent formatting across all companies"""
    # Prepare data for DataFrame
    data = {}
    
    # Add company columns
    for company in all_companies:
        company_name = company["name"]
        data[company_name] = {}
        
        # Add metrics for this company
        for metric in metrics_list:
            metric_id = metric["id"]
            metric_value = get_competitor_metric(company, metric_id)
            
            # Store the raw numeric value
            data[company_name][metric_id] = metric_value
    
    # Create DataFrame
    df = pd.DataFrame(data)
    
    # Add metric names as index
    metric_names = [metric["name"] for metric in metrics_list]
    df.index = metric_names
    
    return df

def save_standardized_excel(df, all_companies, output_dir, company_name):
    """Save standardized data to Excel with basic formatting"""
    company_slug = company_name.lower().replace(' ', '_')
    current_date = datetime.datetime.now().strftime("%Y%m%d")
    excel_filename = os.path.join(output_dir, f"{company_slug}_comparison_{current_date}.xlsx")
    
    try:
        # Format the DataFrame with appropriate display values before saving
        formatted_df = df.copy()
        
        # Format each column
        for col in formatted_df.columns:
            # Apply formatting to each cell based on metric type
            for idx, metric_name in enumerate(formatted_df.index):
                value = formatted_df.loc[metric_name, col]
                metric_id = metrics_list[idx]["id"]
                
                if pd.isna(value) or value is None:
                    formatted_df.loc[metric_name, col] = "Missing value"
                else:
                    # Apply type-specific formatting
                    if metric_id in ["revenue_growth", "gross_margin", "ebitda_margin", "rd_percentage"]:
                        formatted_df.loc[metric_name, col] = f"{value:.1f}%"
                    elif metric_id == "annual_revenue":
                        formatted_df.loc[metric_name, col] = f"${value:,.0f}M"
                    elif metric_id == "operating_cash_flow":
                        formatted_df.loc[metric_name, col] = f"${value:,.0f}M"
                    elif metric_id == "market_capitalization":
                        formatted_df.loc[metric_name, col] = f"${value:,.0f}M"
                    elif metric_id == "employee_count":
                        try:
                            formatted_df.loc[metric_name, col] = f"{int(value):,}"
                        except:
                            formatted_df.loc[metric_name, col] = str(value)
        
        # Save to Excel - simple version without advanced formatting
        formatted_df.to_excel(excel_filename)
        print(f"Saved Excel comparison: {excel_filename}")
        return excel_filename
        
    except Exception as e:
        print(f"Error saving Excel file: {e}")
        print("Falling back to CSV only")
        return None

def main():
    print("\n" + "="*60)
    print(" COMPETITOR DATA COMPARISON ".center(60, "="))
    print("="*60 + "\n")
    
    # Look for the latest competitor analysis
    competitor_dir = "competitor_analysis"
    if not os.path.exists(competitor_dir):
        print(f"No competitor analysis directory found at {competitor_dir}")
        return
    
    # Find all company directories in the competitor analysis directory
    company_dirs = [d for d in os.listdir(competitor_dir) if os.path.isdir(os.path.join(competitor_dir, d))]
    
    if not company_dirs:
        print(f"No company analysis found in {competitor_dir}")
        return
    
    print(f"Found {len(company_dirs)} company analyses:")
    for i, company_dir in enumerate(company_dirs):
        print(f"  {i+1}. {company_dir}")
    
    selected_company = company_dirs[0]
    if len(company_dirs) > 1:
        selection = input(f"Select a company (1-{len(company_dirs)}) [default: 1]: ")
        if selection:
            try:
                index = int(selection) - 1
                if 0 <= index < len(company_dirs):
                    selected_company = company_dirs[index]
            except ValueError:
                pass
    
    company_dir = os.path.join(competitor_dir, selected_company)
    print(f"\nUsing company analysis: {selected_company}")
    
    # Find the latest competitor financials file
    financials_file = get_latest_file(company_dir, "*competitor_financials_*.json")
    if not financials_file:
        print(f"No competitor financials found in {company_dir}")
        return
    
    print(f"Using competitor financials: {os.path.basename(financials_file)}")
    
    # Find the input company data file
    company_name = selected_company.replace('_', ' ').title()
    default_input_path = f"financial_data/{selected_company}/{selected_company}_financial_metrics.json"
    
    if os.path.exists(default_input_path):
        input_company_path = default_input_path
    else:
        # Look for financial metrics files
        metrics_files = []
        for root, dirs, files in os.walk("financial_data"):
            for file in files:
                if file.endswith("_financial_metrics.json"):
                    metrics_files.append(os.path.join(root, file))
        
        if not metrics_files:
            print("No input company files found. Please provide the path to the input company file:")
            input_company_path = input("File path: ")
        else:
            print(f"Found {len(metrics_files)} input company files:")
            for i, file_path in enumerate(metrics_files):
                print(f"  {i+1}. {file_path}")
            
            selection = input(f"Select an input company file (1-{len(metrics_files)}) [default: 1]: ")
            if selection:
                try:
                    index = int(selection) - 1
                    if 0 <= index < len(metrics_files):
                        input_company_path = metrics_files[index]
                    else:
                        input_company_path = metrics_files[0]
                except ValueError:
                    input_company_path = metrics_files[0]
            else:
                input_company_path = metrics_files[0]
    
    print(f"Using input company data: {os.path.basename(input_company_path)}")
    
    # Load input company data
    input_company_data = load_json_file(input_company_path)
    if not input_company_data:
        print("Failed to load input company data")
        return
    
    print(f"\nCombining data for {input_company_data.get('company_name', 'Unknown')} with competitors...")
    
    # Combine the data
    all_companies = combine_company_data(input_company_path, financials_file)
    if not all_companies:
        print("Failed to combine company data")
        return
    
    # Define metrics list for standardized processing
    global metrics_list
    metrics_list = [
        {"id": "annual_revenue", "name": "Annual Revenue"},
        {"id": "revenue_growth", "name": "Revenue Growth"},
        {"id": "gross_margin", "name": "Gross Margin"},
        {"id": "ebitda_margin", "name": "EBITDA Margin"},
        {"id": "rd_percentage", "name": "R&D % of Revenue"},
        {"id": "operating_cash_flow", "name": "Operating Cash Flow"},
        {"id": "employee_count", "name": "Employee Count"},
        {"id": "market_capitalization", "name": "Market Cap"}
    ]
    
    # Add industry-specific metrics if any company has them
    for company in all_companies:
        metrics = company.get("metrics", {})
        if "pipeline_products" in metrics and not any(m["id"] == "pipeline_products" for m in metrics_list):
            metrics_list.append({"id": "pipeline_products", "name": "Pipeline Products"})
        if "clinical_trials" in metrics and not any(m["id"] == "clinical_trials" for m in metrics_list):
            metrics_list.append({"id": "clinical_trials", "name": "Clinical Trials"})
    
    # Create standardized DataFrame
    df = create_standardized_dataframe(all_companies, metrics_list)
    
    # Save the standardized Excel file
    output_dir = company_dir
    excel_file = save_standardized_excel(df, all_companies, output_dir, input_company_data.get('company_name', 'company'))
    
    # Also create and save the comparison table in CSV and JSON formats
    comparison_table = create_comparison_table(all_companies)
    csv_file, json_file = save_comparison_data(input_company_data, comparison_table, output_dir)
    
    print("\n✅ Data combination complete!")
    
    # Display a preview of the DataFrame
    print("\nStandardized Data Preview:")
    print(df.head())
    
    print(f"\nFull comparison saved to:")
    if excel_file:
        print(f"  Excel: {excel_file}")
    print(f"  CSV: {csv_file}")
    print(f"  JSON: {json_file}")
    
    # Also save as HTML for easy viewing
    html_filename = os.path.join(output_dir, f"{company_slug}_comparison_{datetime.datetime.now().strftime('%Y%m%d')}.html")
    
    # Convert the DataFrame to HTML with formatting
    html_content = """
    <html>
    <head>
        <title>Competitor Comparison</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; }
            table { border-collapse: collapse; width: 100%; }
            th, td { padding: 8px; text-align: right; border: 1px solid #ddd; }
            th { background-color: #f2f2f2; }
            tr:nth-child(even) { background-color: #f9f9f9; }
            .metric-name { text-align: left; font-weight: bold; }
            .missing { color: #999; }
            h1 { color: #333; }
        </style>
    </head>
    <body>
        <h1>Competitor Analysis: {company}</h1>
        <p>Generated on {date}</p>
        <table>
            <tr>
                <th class="metric-name">Metric</th>
                {headers}
            </tr>
            {rows}
        </table>
    </body>
    </html>
    """
    
    # Generate table headers
    headers = ""
    for company in df.columns:
        headers += f"<th>{company}</th>"
    
    # Generate table rows
    rows = ""
    for metric in df.index:
        rows += f"<tr><td class='metric-name'>{metric}</td>"
        for company in df.columns:
            value = df.loc[metric, company]
            if pd.isna(value) or value is None:
                rows += "<td class='missing'>Missing value</td>"
            else:
                metric_id = next((m["id"] for m in metrics_list if m["name"] == metric), "")
                
                # Format based on metric type
                if metric_id in ["revenue_growth", "gross_margin", "ebitda_margin", "rd_percentage"]:
                    formatted_value = f"{value:.1f}%" if isinstance(value, (int, float)) else str(value)
                elif metric_id in ["annual_revenue", "operating_cash_flow", "market_capitalization"]:
                    formatted_value = f"${value:,.0f}M" if isinstance(value, (int, float)) else str(value)
                elif metric_id == "employee_count":
                    formatted_value = f"{int(value):,}" if isinstance(value, (int, float)) else str(value)
                else:
                    formatted_value = f"{value:,}" if isinstance(value, (int, float)) else str(value)
                
                rows += f"<td>{formatted_value}</td>"
        rows += "</tr>"
    
    # Fill in the template
    html_content = html_content.format(
        company=input_company_data.get('company_name', 'Company'),
        date=datetime.datetime.now().strftime("%Y-%m-%d"),
        headers=headers,
        rows=rows
    )
    
    # Save the HTML file
    with open(html_filename, 'w') as f:
        f.write(html_content)
    
    print(f"  HTML: {html_filename}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nOperation cancelled by user.")
    except Exception as e:
        print(f"\n\nAn error occurred: {str(e)}")
        import traceback
        traceback.print_exc()
    finally:
        print("\nExiting program.")