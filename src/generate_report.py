import os
import pandas as pd
import json
import requests
import glob
import argparse
from fpdf import FPDF
from datetime import datetime
from pathlib import Path

# Set up argument parsing
parser = argparse.ArgumentParser(description='Generate financial analysis report')
parser.add_argument('--csv', help='Path to the comparison CSV file')
parser.add_argument('--auto', action='store_true', help='Run in automatic mode without prompts')
parser.add_argument('--output-dir', help='Custom output directory for report files')
parser.add_argument('--charts-dir', help='Directory containing chart images to include in the report')
args = parser.parse_args()

# Try to load environment variables, gracefully handle if dotenv not available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    print("Note: dotenv module not found, using existing environment variables")

# Get API keys from environment variables
API_KEY = os.environ.get("API_KEY")
API_URL = os.environ.get("API_URL")

COMP_ANALYSIS_DIR = os.path.join(os.path.dirname(__file__), "..", "competitor_analysis")

# Map of industry keywords to specific analysis points
INDUSTRY_ANALYSIS_GUIDES = {
    "tech": """
- Focus on R&D as percentage of revenue and its impact on innovation
- Evaluate recurring revenue models and customer acquisition costs
- Assess operational efficiency metrics like revenue per employee
- Analyze growth rate relative to market maturity
""",
    "pharma": """
- Evaluate R&D pipeline and clinical trial progress
- Assess gross margin as indicator of pricing power
- Compare research investment relative to peers
- Consider market share in key therapeutic areas
""",
    "retail": """
- Analyze inventory turnover and same-store sales metrics
- Evaluate gross margin as indicator of pricing power and brand strength
- Consider employee count in context of automation and efficiency
- Assess market share and growth relative to total addressable market
""",
    "financial": """
- Focus on risk metrics and capital adequacy
- Evaluate operational efficiency and cost management
- Assess growth in context of economic cycle position
- Consider regulatory constraints on business model
""",
    "energy": """
- Analyze operating cash flow resilience through price cycles
- Evaluate capital expenditure efficiency 
- Consider sustainability metrics and regulatory impacts
- Assess production efficiency and resource replacement rates
"""
}

def detect_industry(company_folder):
    """Attempt to detect industry from available data"""
    # Try to find any JSON files with company info
    json_files = glob.glob(os.path.join(company_folder, "*.json"))
    for file_path in json_files:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # Check various potential structures
                if isinstance(data, dict):
                    # Check for industry field at various levels
                    if 'industry' in data:
                        return data['industry']
                    elif 'company_metrics' in data and len(data['company_metrics']) > 0:
                        if 'industry' in data['company_metrics'][0]:
                            return data['company_metrics'][0]['industry']
                    # Try other potential locations
                    for key, value in data.items():
                        if isinstance(value, dict) and 'industry' in value:
                            return value['industry']
        except:
            continue
    
    # Default to unknown if no industry found
    return "Unknown"

def get_industry_guide(industry):
    """Get industry-specific analysis guidance"""
    industry_lower = industry.lower()
    
    for key, guide in INDUSTRY_ANALYSIS_GUIDES.items():
        if key in industry_lower:
            return guide
    
    # Return generic guide if no specific industry match
    return """
- Evaluate revenue growth trajectory relative to industry average
- Assess margin profile and operational efficiency
- Consider competitive positioning and market share trends
- Analyze cash flow generation and capital allocation efficiency
"""

def load_csv_summary(csv_path):
    """Load and format competitive comparison data for analysis"""
    df = pd.read_csv(csv_path)
    
    # Extract target company (assumed to be first column after Metric)
    target_company = df.columns[1] if len(df.columns) > 1 else "Target Company"
    
    # Extract all competitor names
    competitors = [col for col in df.columns if col != "Metric"]
    
    # Format data for report
    summary = []
    summary.append(f"# Competitive Analysis: {target_company} vs. {len(competitors)-1} Competitors")
    summary.append("")
    
    # Create a table for basic metrics
    summary.append("## Key Metrics Table:")
    
    # Format with better structure for analysis
    for _, row in df.iterrows():
        metric = row["Metric"]
        summary.append(f"\n### {metric}")
        
        # Target company value first
        target_value = row.get(target_company, "N/A")
        summary.append(f"* {target_company}: {target_value}")
        
        # Get values for all companies to calculate average
        numeric_values = []
        for company, value in row.items():
            if company != "Metric" and company != target_company:
                summary.append(f"* {company}: {value}")
                try:
                    # Try to extract numeric value for average calculation
                    clean_value = str(value).replace('$', '').replace('%', '').replace('M', '').replace(',', '')
                    numeric_values.append(float(clean_value))
                except:
                    pass
        
        # Calculate competitor average if possible
        if numeric_values:
            competitor_avg = sum(numeric_values) / len(numeric_values)
            metric_type = metric.lower()
            
            if "margin" in metric_type or "growth" in metric_type or "percentage" in metric_type:
                avg_formatted = f"{competitor_avg:.1f}%"
            elif "revenue" in metric_type or "cash" in metric_type or "cap" in metric_type:
                avg_formatted = f"${competitor_avg:.1f}M"
            elif "employee" in metric_type:
                avg_formatted = f"{int(competitor_avg):,}"
            else:
                avg_formatted = f"{competitor_avg:.2f}"
                
            summary.append(f"* **Competitor Average**: {avg_formatted}")
        
        summary.append("")
    
    return "\n".join(summary), target_company

def find_chart_images(company_folder, specified_charts_dir=None):
    """Find all chart images for the company analysis"""
    # Use explicitly provided charts directory if available
    if specified_charts_dir and os.path.exists(specified_charts_dir):
        print(f"Using specified charts directory: {specified_charts_dir}")
        chart_files = glob.glob(os.path.join(specified_charts_dir, "*.png"))
        if chart_files:
            # Filter out the dashboard summary
            chart_files = [f for f in chart_files if "dashboard" not in os.path.basename(f).lower()]
            return chart_files
    
    # Try enhanced charts directory
    enhanced_charts_dir = os.path.join(company_folder, "enhanced_charts")
    if os.path.exists(enhanced_charts_dir):
        chart_files = glob.glob(os.path.join(enhanced_charts_dir, "*.png"))
        if chart_files:
            # Filter out the dashboard summary
            chart_files = [f for f in chart_files if "dashboard" not in os.path.basename(f).lower()]
            return chart_files
    
    # Try regular charts directory
    charts_dir = os.path.join(company_folder, "charts")
    if os.path.exists(charts_dir):
        chart_files = glob.glob(os.path.join(charts_dir, "*.png"))
        if chart_files:
            return chart_files
    
    # No chart files found
    return []

def generate_analysis(summary_text, company_name, industry):
    """Generate financial analysis report using AI"""
    if not API_KEY or not API_URL:
        print("Warning: API_KEY or API_URL not set in environment variables.")
        print("Using placeholder report instead.")
        return f"""# Financial Analysis Report for {company_name}

## 1. Executive Summary
This is a placeholder report. To generate a real report, please set API_KEY and API_URL environment variables.

## 2. Competitive Position Analysis
A detailed analysis would be presented here using the OpenAI API.

## 3. Financial Performance Deep Dive
Financial metrics would be analyzed here.

## 4. Risk Assessment
Key risks would be identified here.

## 5. Strategic Recommendations
Strategic recommendations would be made here.
"""
    
    headers = {
        "Content-Type": "application/json",
        "api-key": API_KEY
    }

    # Get industry-specific guidance
    industry_guide = get_industry_guide(industry)

    prompt = f"""
You are a senior financial analyst with extensive experience in the {industry} industry. 
Given the data below comparing {company_name} to its public competitors,
write a comprehensive financial analysis report with the following sections:

## 1. Executive Summary (100-150 words)
A concise overview of the key findings, highlighting the most important competitive advantages or challenges.

## 2. Competitive Position Analysis (150-200 words)
Analysis of {company_name}'s market positioning relative to competitors.
Identify specific strengths and weaknesses based on the metrics provided.

## 3. Financial Performance Deep Dive (200-250 words)
Detailed analysis of financial metrics including:
- Revenue and growth trajectory
- Margin analysis (gross and EBITDA)
- Operational efficiency
- R&D investment and innovation indicators
{industry_guide}

## 4. Risk Assessment (100-150 words)
Identify key risks and vulnerabilities based on the comparative metrics.
Highlight potential red flags that warrant further investigation.

## 5. Strategic Recommendations (150-200 words)
Provide 3-5 specific, actionable recommendations for {company_name} based on this competitive analysis.
Focus on strategic priorities to improve competitive positioning.

DATA ANALYSIS:
{summary_text}

IMPORTANT INSTRUCTIONS:
1. Use specific metric values to support your analysis
2. Compare to both individual competitors and industry averages
3. Provide actionable insights, not just observations
4. Consider both short-term performance and long-term strategic implications
5. Be candid about both strengths and weaknesses
6. Make your recommendations specific and actionable
"""

    try:
        body = {
            "messages": [
                {"role": "system", "content": "You are a senior financial analyst providing competitive analysis for portfolio companies."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.7,
            "max_tokens": 2000
        }

        response = requests.post(API_URL, headers=headers, data=json.dumps(body))
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"Error generating report: {e}")
        return f"""# Financial Analysis Report for {company_name}

## 1. Executive Summary
An error occurred while generating the report: {str(e)}

## 2. Competitive Position Analysis
Unable to generate due to API error.

## 3. Financial Performance Deep Dive
Unable to generate due to API error.

## 4. Risk Assessment
Unable to generate due to API error.

## 5. Strategic Recommendations
Unable to generate due to API error.
"""

def save_text_report(report_text, output_path):
    """Save report as plain text file"""
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report_text)
    print(f"Text report saved to: {output_path}")

def create_pdf_report(report_text, output_path, company_name, chart_files=None):
    """Create a formatted PDF report with embedded charts"""
    try:
        class PDF(FPDF):
            def header(self):
                # Arial bold 15
                self.set_font('Arial', 'B', 15)
                # Move to the right
                self.cell(80)
                # Title
                self.cell(30, 10, f'Competitive Analysis: {company_name}', 0, 0, 'C')
                # Line break
                self.ln(20)

            def footer(self):
                # Position at 1.5 cm from bottom
                self.set_y(-15)
                # Arial italic 8
                self.set_font('Arial', 'I', 8)
                # Page number
                self.cell(0, 10, 'Page ' + str(self.page_no()) + '/{nb}', 0, 0, 'C')
                # Date
                self.set_x(10)
                self.cell(0, 10, f'Generated on {datetime.now().strftime("%Y-%m-%d")}', 0, 0, 'L')

            def chapter_title(self, title):
                # Arial 12
                self.set_font('Arial', 'B', 12)
                # Background color
                self.set_fill_color(200, 220, 255)
                # Title
                self.cell(0, 6, title, 0, 1, 'L', 1)
                # Line break
                self.ln(4)

            def chapter_body(self, body):
                # Times 12
                self.set_font('Arial', '', 11)
                # Output justified text
                self.multi_cell(0, 5, body)
                # Line break
                self.ln()

        # Create PDF object
        pdf = PDF()
        pdf.alias_nb_pages()
        pdf.add_page()
        pdf.set_auto_page_break(auto=True, margin=15)

        # Title
        pdf.set_font('Arial', 'B', 16)
        pdf.cell(0, 10, f"Competitive Analysis Report", 0, 1, 'C')
        pdf.cell(0, 10, f"{company_name}", 0, 1, 'C')
        pdf.ln(10)
        
        # Process and add content
        sections = report_text.split('##')
        
        for section in sections:
            if not section.strip():
                continue
            
            # Extract section title and content
            lines = section.strip().split('\n')
            title = lines[0].strip()
            content = '\n'.join(lines[1:]).strip()
            
            # Add to PDF
            pdf.chapter_title(title)
            pdf.chapter_body(content)
            pdf.ln(5)
        
        # Add charts if available
        if chart_files:
            pdf.add_page()
            pdf.chapter_title("Competitive Analysis Charts")
            
            # Determine how many charts to include (max 6 for readability)
            charts_to_include = chart_files[:6]
            
            # Add some intro text
            pdf.chapter_body("The following charts provide visual representation of key metrics comparing the target company with competitors.")
            pdf.ln(5)
            
            # Calculate dimensions for charts (2 columns)
            chart_width = 90  # mm
            chart_height = 70  # mm
            
            # Add charts
            for i, chart_file in enumerate(charts_to_include):
                x_pos = 10 if i % 2 == 0 else 105
                y_pos = pdf.get_y()
                
                # If we're starting a new row on right side, don't adjust y
                if i % 2 == 0 and i > 0:
                    pdf.set_y(y_pos)
                    
                # Add the chart
                try:
                    pdf.image(chart_file, x=x_pos, y=y_pos, w=chart_width, h=chart_height)
                    
                    # Add caption
                    chart_name = os.path.basename(chart_file).replace('.png', '').replace('_', ' ').title()
                    pdf.set_y(y_pos + chart_height + 2)
                    pdf.set_x(x_pos)
                    pdf.set_font('Arial', 'I', 8)
                    pdf.cell(chart_width, 5, chart_name, 0, 1, 'C')
                    
                    # Move to next row if we just added right column chart
                    if i % 2 == 1:
                        pdf.ln(5)
                    # If it's the last chart and it's in the left column, move down
                    elif i == len(charts_to_include) - 1:
                        pdf.ln(chart_height + 10)
                except Exception as e:
                    print(f"Error adding chart {chart_file}: {e}")
                    pdf.ln(5)
        
        # Save PDF
        pdf.output(output_path)
        print(f"PDF report with charts saved to: {output_path}")
        return True
    except Exception as e:
        print(f"Error creating PDF report: {e}")
        print("Falling back to text report only")
        return False

def get_available_companies():
    """Get list of available companies for analysis"""
    if not os.path.exists(COMP_ANALYSIS_DIR):
        return []
    
    folders = [d for d in os.listdir(COMP_ANALYSIS_DIR)
               if os.path.isdir(os.path.join(COMP_ANALYSIS_DIR, d))]
    return folders

def get_latest_csv(folder_path):
    """Get the most recent comparison CSV file"""
    csv_files = sorted(
        glob.glob(os.path.join(folder_path, "*_comparison_*.csv")),
        key=os.path.getmtime,
        reverse=True
    )
    return csv_files[0] if csv_files else None

def main():
    print("\n" + "="*70)
    print(" ENHANCED FINANCIAL ANALYSIS REPORT GENERATOR ".center(70, "="))
    print("="*70 + "\n")
    
    # Check for required dependencies
    try:
        import fpdf
    except ImportError:
        print("FPDF package not found. Installing...")
        import subprocess
        try:
            subprocess.check_call(["pip", "install", "fpdf"])
            print("FPDF installed successfully")
        except:
            print("Could not install FPDF. Reports will be generated as text only.")
    
    # Get CSV file path from arguments or environment variables
    csv_file = args.csv or os.environ.get("REPORT_CSV_PATH")
    auto_mode = args.auto or os.environ.get("AUTO_SELECT_FIRST") == "1"
    
    if not csv_file:
        # Original interactive file selection code
        companies = get_available_companies()
        if not companies:
            print("No companies found in 'competitor_analysis'")
            return

        print("\nAvailable company analyses:")
        for i, comp in enumerate(companies, 1):
            print(f"  {i}. {comp.replace('_', ' ').title()}")

        selection = input(f"\nSelect a company (1-{len(companies)}): ").strip()
        try:
            index = int(selection) - 1
            if index < 0 or index >= len(companies):
                raise ValueError
        except ValueError:
            print("Invalid selection.")
            return

        company_folder = os.path.join(COMP_ANALYSIS_DIR, companies[index])
        company_name = companies[index].replace("_", " ").title()
        csv_file = get_latest_csv(company_folder)

        if not csv_file:
            print(f"No comparison CSV found in {company_name}")
            return
    else:
        print(f"\nUsing CSV: {os.path.basename(csv_file)}")
        # Derive company name and folder from CSV path
        company_folder = os.path.dirname(csv_file)
        company_name = os.path.basename(company_folder).replace("_", " ").title()
        
    print(f"Processing data for: {company_name}")
    
    # Detect industry
    industry = detect_industry(company_folder)
    print(f"Detected industry: {industry}")
    
    # Find chart files - now using the charts-dir parameter if provided
    if args.charts_dir:
        print(f"Using charts directory from parameter: {args.charts_dir}")
        chart_files = find_chart_images(company_folder, args.charts_dir)
    else:
        chart_files = find_chart_images(company_folder)
        
    if chart_files:
        print(f"Found {len(chart_files)} chart images for visualization")
    else:
        print("No chart images found. Report will be text-only.")
    
    # Load and format data
    try:
        summary_text, target_company = load_csv_summary(csv_file)
    except Exception as e:
        print(f"Error loading CSV data: {e}")
        return
        
    if target_company != company_name and not auto_mode:
        print(f"Target company in data appears to be: {target_company}")
        confirmation = input(f"Use '{target_company}' instead of '{company_name}'? (Y/n): ")
        if confirmation.lower() not in ('n', 'no'):
            company_name = target_company
    elif target_company != company_name and auto_mode:
        print(f"Target company in data appears to be: {target_company}")
        print(f"Automatically using '{target_company}' in auto mode")
        company_name = target_company
    
    print("\nGenerating comprehensive financial analysis...")
    report = generate_analysis(summary_text, company_name, industry)

    # Determine output directory
    if args.output_dir:
        output_dir = args.output_dir
        os.makedirs(output_dir, exist_ok=True)
        output_base = os.path.join(output_dir, os.path.splitext(os.path.basename(csv_file))[0])
    else:
        output_base = os.path.splitext(csv_file)[0]
    
    # Save as text file
    output_txt = f"{output_base}_financial_analysis.txt"
    save_text_report(report, output_txt)
    
    # Create PDF version with charts
    output_pdf = f"{output_base}_financial_analysis.pdf"
    pdf_success = create_pdf_report(report, output_pdf, company_name, chart_files)
    
    print("\nFinancial analysis report generation complete!")
    print("\nReport includes:")
    print("  - Executive Summary")
    print("  - Competitive Position Analysis")
    print("  - Financial Performance Deep Dive")
    print("  - Risk Assessment")
    print("  - Strategic Recommendations")
    if pdf_success and chart_files:
        print("  - Visual Competitive Analysis Charts")

if __name__ == "__main__":
    main()