import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter
import seaborn as sns
import argparse
from pathlib import Path

# Set up argument parsing
parser = argparse.ArgumentParser(description='Generate PowerBI-style visualization charts')
parser.add_argument('--csv', help='Path to the comparison CSV file')
parser.add_argument('--auto', action='store_true', help='Run in automatic mode without prompts')
parser.add_argument('--output-dir', help='Custom output directory for charts')
args = parser.parse_args()

def to_numeric(val):
    """Convert cleaned string values like $1,234M or 78.2% to numeric"""
    if isinstance(val, str):
        val = val.replace('$', '').replace('%', '').replace('M', '').replace(',', '').strip()
        try:
            return float(val)
        except ValueError:
            return None
    return val

def format_label(value, metric_type):
    """Format labels based on metric type"""
    if pd.isna(value):
        return ""
    
    if "margin" in metric_type.lower() or "growth" in metric_type.lower() or "percentage" in metric_type.lower():
        return f"{value:.1f}%"
    elif "revenue" in metric_type.lower() or "cash flow" in metric_type.lower() or "cap" in metric_type.lower():
        return f"${value:.0f}M"
    elif "employee" in metric_type.lower():
        return f"{value:,.0f}"
    else:
        return f"{value:.1f}"

def find_all_comparison_csvs(base_dir="competitor_analysis"):
    """Search recursively in competitor_analysis for all _comparison_ CSVs"""
    base_dir = os.path.abspath(base_dir)
    csv_files = []
    for root, dirs, files in os.walk(base_dir):
        for file in files:
            if file.endswith(".csv") and "_comparison_" in file:
                full_path = os.path.join(root, file)
                csv_files.append(full_path)
    return csv_files

def format_y_axis(ax, metric):
    """Format y-axis based on metric type"""
    metric_lower = metric.lower()
    
    if "margin" in metric_lower or "growth" in metric_lower or "percentage" in metric_lower:
        ax.yaxis.set_major_formatter(FuncFormatter(lambda x, _: f'{x:.1f}%'))
        ax.set_ylabel(f"{metric} (%)")
    elif "revenue" in metric_lower or "cash flow" in metric_lower or "cap" in metric_lower:
        ax.yaxis.set_major_formatter(FuncFormatter(lambda x, _: f'${x:.0f}M'))
        ax.set_ylabel(f"{metric} ($ Millions)")
    elif "employee" in metric_lower:
        ax.yaxis.set_major_formatter(FuncFormatter(lambda x, _: f'{x:,.0f}'))
        ax.set_ylabel(f"{metric} (Count)")
    else:
        ax.set_ylabel(metric)

def calculate_industry_average(values):
    """Calculate the industry average excluding missing values"""
    return values.dropna().mean()

def find_related_metrics(metric, all_metrics):
    """Find related metrics for combo charts"""
    metric_lower = metric.lower()
    
    # Define related pairs
    if "revenue" in metric_lower and "growth" not in metric_lower:
        return "Revenue Growth" if "Revenue Growth" in all_metrics else None
    elif "margin" in metric_lower:
        if "gross" in metric_lower:
            return "EBITDA Margin" if "EBITDA Margin" in all_metrics else None
        elif "ebitda" in metric_lower:
            return "Gross Margin" if "Gross Margin" in all_metrics else None
    
    return None

def create_combo_chart(metric1, metric2, df1, df2, target_company, charts_dir):
    """Create a combo chart with two related metrics"""
    fig, ax1 = plt.figure(figsize=(12, 7), dpi=100), plt.gca()
    
    # Get data
    values1 = df1.loc[metric1].dropna().sort_values(ascending=False)
    values2 = df2.loc[metric2]
    
    # Reindex the second metric to match the first (sorted) metric
    values2 = values2.reindex(values1.index)
    
    # Create bar chart for first metric
    colors = ['#3366CC' if company != target_company else '#FF9900' for company in values1.index]
    bars = ax1.bar(values1.index, values1.values, color=colors, alpha=0.7)
    
    # Format first axis
    format_y_axis(ax1, metric1)
    
    # Add industry average line for first metric
    avg1 = calculate_industry_average(values1)
    ax1.axhline(y=avg1, color='#3366CC', linestyle='--', alpha=0.7, label=f'{metric1} Industry Avg: {format_label(avg1, metric1)}')
    
    # Create second axis and plot line chart
    ax2 = ax1.twinx()
    ax2.plot(values1.index, values2.values, marker='o', color='#FF5733', linewidth=2, label=metric2)
    
    # Format second axis
    format_y_axis(ax2, metric2)
    
    # Add industry average line for second metric
    avg2 = calculate_industry_average(values2)
    ax2.axhline(y=avg2, color='#FF5733', linestyle='--', alpha=0.7, label=f'{metric2} Industry Avg: {format_label(avg2, metric2)}')
    
    # Add value labels to bars
    for bar, value in zip(bars, values1.values):
        if not np.isnan(value):
            height = bar.get_height()
            ax1.text(bar.get_x() + bar.get_width()/2., height,
                    format_label(value, metric1),
                    ha='center', va='bottom', rotation=0)
    
    # Configure legend and layout
    h1, l1 = ax1.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax1.legend(h1+h2, l1+l2, loc='upper right')
    
    plt.title(f"{metric1} vs {metric2} Comparison", fontsize=16, pad=20)
    plt.xticks(rotation=45, ha='right')
    plt.tight_layout()
    
    # Save the figure
    chart_file = os.path.join(charts_dir, f"{metric1.replace(' ', '_').lower()}_vs_{metric2.replace(' ', '_').lower()}.png")
    plt.savefig(chart_file, bbox_inches='tight')
    plt.close()
    
    print(f"Saved combo chart: {chart_file}")
    return chart_file

def main():
    print("\n" + "="*70)
    print(" ENHANCED POWER BI STYLE CHART GENERATOR ".center(70, "="))
    print("="*70 + "\n")

    # Set the style for more professional looking charts
    plt.style.use('seaborn-v0_8-whitegrid')
    sns.set_palette("colorblind")

    # Get CSV file path from arguments or environment variables
    csv_path = args.csv or os.environ.get("CHART_CSV_PATH")
    auto_mode = args.auto or os.environ.get("AUTO_SELECT") == "1"
    
    if not csv_path:
        # 1. Locate all comparison CSVs - original interactive code
        csv_files = find_all_comparison_csvs()
        if not csv_files:
            print("No comparison CSV files found.")
            return

        print("Found the following comparison CSV files:")
        for i, file_path in enumerate(csv_files):
            print(f"  {i+1}. {file_path}")

        # 2. User selects which one to use
        selection = input(f"\nSelect a file to generate PowerBI-style charts (1-{len(csv_files)}): ")
        try:
            index = int(selection) - 1
            selected_csv = csv_files[index]
        except (ValueError, IndexError):
            print("Invalid selection. Exiting.")
            return
    else:
        selected_csv = csv_path
        print(f"\nUsing specified CSV file: {selected_csv}")

    print(f"\nLoading data from: {selected_csv}")
    df = pd.read_csv(selected_csv, index_col=0)
    
    # Identify target company (assuming it's the first column)
    target_company = df.columns[0]
    
    if not auto_mode:
        # Ask user to confirm or select target company - original interactive code
        print(f"\nDetected target company: {target_company}")
        confirmation = input(f"Is this correct? (Y/n) or enter the correct company name: ")
        if confirmation.lower() not in ('', 'y', 'yes'):
            if confirmation.lower() in ('n', 'no'):
                print("Available companies:")
                for i, company in enumerate(df.columns):
                    print(f"  {i+1}. {company}")
                company_selection = input("Select target company number: ")
                try:
                    company_index = int(company_selection) - 1
                    target_company = df.columns[company_index]
                except (ValueError, IndexError):
                    print("Invalid selection, using first company as target.")
            else:
                # User provided a company name directly
                if confirmation in df.columns:
                    target_company = confirmation
                else:
                    print(f"Company '{confirmation}' not found in data. Using first company as target.")
    else:
        print(f"Using {target_company} as the target company in auto mode.")

    # 3. Convert values to numeric
    df_numeric = df.applymap(to_numeric)

    # 4. Create output folder
    if args.output_dir:
        charts_dir = args.output_dir
    else:
        charts_dir = os.path.join(os.path.dirname(selected_csv), "enhanced_charts")
    
    os.makedirs(charts_dir, exist_ok=True)
    print(f"Charts will be saved to: {charts_dir}")

    # 5. Generate enhanced individual charts
    generated_charts = []
    for metric in df_numeric.index:
        plt.figure(figsize=(12, 7), dpi=100)
        values = df_numeric.loc[metric].dropna()
        sorted_values = values.sort_values(ascending=False)
        
        # Calculate industry average
        industry_avg = calculate_industry_average(values)
        
        # Create bar chart with special color for target company
        colors = ['#3366CC' if company != target_company else '#FF9900' for company in sorted_values.index]
        bars = plt.bar(sorted_values.index, sorted_values.values, color=colors)
        
        # Add value labels on top of each bar
        for bar, value in zip(bars, sorted_values.values):
            if not np.isnan(value):
                height = bar.get_height()
                plt.text(bar.get_x() + bar.get_width()/2., height,
                        format_label(value, metric),
                        ha='center', va='bottom', rotation=0)
        
        # Add industry average line
        plt.axhline(y=industry_avg, color='red', linestyle='--', alpha=0.7)
        plt.text(0.02, 0.95, f'Industry Average: {format_label(industry_avg, metric)}', 
                 transform=plt.gca().transAxes, fontsize=12, 
                 verticalalignment='top', bbox=dict(boxstyle='round,pad=0.5', facecolor='white', alpha=0.7))
        
        # Format the Y-axis based on metric type
        ax = plt.gca()
        format_y_axis(ax, metric)
        
        # Add title and adjust layout
        plt.title(f"{metric} Comparison", fontsize=16, pad=20)
        plt.xticks(rotation=45, ha='right')
        plt.tight_layout()
        
        # Add legend for target company vs competitors
        from matplotlib.patches import Patch
        legend_elements = [
            Patch(facecolor='#FF9900', label='Target Company'),
            Patch(facecolor='#3366CC', label='Competitors')
        ]
        plt.legend(handles=legend_elements, loc='upper right')

        # Save chart
        chart_file = os.path.join(charts_dir, f"{metric.replace(' ', '_').lower()}.png")
        plt.savefig(chart_file, bbox_inches='tight')
        generated_charts.append(chart_file)
        print(f"Saved chart: {chart_file}")
        plt.close()

    # 6. Generate combo charts for related metrics
    already_paired = set()
    for metric in df_numeric.index:
        if metric in already_paired:
            continue
            
        related_metric = find_related_metrics(metric, df_numeric.index)
        if related_metric and related_metric not in already_paired:
            chart_file = create_combo_chart(metric, related_metric, df_numeric, df_numeric, target_company, charts_dir)
            generated_charts.append(chart_file)
            already_paired.add(metric)
            already_paired.add(related_metric)

    # 7. Create a dashboard with thumbnails of all charts
    try:
        from PIL import Image
        import math
        
        print("\nGenerating dashboard summary...")
        
        # Determine grid size based on number of charts
        num_charts = len(generated_charts)
        cols = min(3, num_charts)
        rows = math.ceil(num_charts / cols)
        
        # Create a summary image with thumbnails
        thumbsize = (400, 300)
        summary_img = Image.new('RGB', (thumbsize[0] * cols, thumbsize[1] * rows), color='white')
        
        for i, chart_path in enumerate(generated_charts):
            if os.path.exists(chart_path):
                try:
                    img = Image.open(chart_path)
                    img.thumbnail(thumbsize)
                    x = (i % cols) * thumbsize[0]
                    y = (i // cols) * thumbsize[1]
                    summary_img.paste(img, (x, y))
                except Exception as e:
                    print(f"Could not add {chart_path} to dashboard: {e}")
        
        dashboard_path = os.path.join(charts_dir, "dashboard_summary.png")
        summary_img.save(dashboard_path)
        print(f"Saved dashboard summary: {dashboard_path}")
    except ImportError:
        print("PIL not installed, skipping dashboard generation")
        print("Install with: pip install Pillow")

    print(f"\nAll enhanced charts generated successfully in {charts_dir}!")
    print("Each chart includes:")
    print(" - Color highlighting for target company")
    print(" - Industry average reference line")
    print(" - Value labels on each bar")
    print(" - Appropriate formatting for each metric type")
    print(" - Combo charts for related metrics")

if __name__ == "__main__":
    main()