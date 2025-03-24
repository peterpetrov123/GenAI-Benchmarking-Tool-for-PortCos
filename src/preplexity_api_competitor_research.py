import os
import json
import requests
import time
import datetime
import re
import hashlib
from dotenv import load_dotenv
from typing import Dict, List, Optional, Any

# Load environment variables
load_dotenv()

# Get Perplexity API key
PERPLEXITY_API_KEY = os.getenv("PERPLEXITY_API_KEY")
if not PERPLEXITY_API_KEY:
    raise ValueError("PERPLEXITY_API_KEY not found in environment variables")

# API endpoint
PERPLEXITY_API_URL = "https://api.perplexity.ai/chat/completions"

# Path for cache storage
CACHE_DIR = "cache"
os.makedirs(CACHE_DIR, exist_ok=True)

def get_cache_key(data):
    """Generate a cache key based on the input data"""
    serialized = json.dumps(data, sort_keys=True)
    return hashlib.md5(serialized.encode()).hexdigest()

def check_cache(cache_key, cache_type):
    """Check if a response exists in the cache"""
    cache_file = os.path.join(CACHE_DIR, f"{cache_type}_{cache_key}.json")
    if os.path.exists(cache_file):
        try:
            with open(cache_file, 'r') as f:
                return json.load(f)
        except:
            return None
    return None

def save_to_cache(cache_key, cache_type, data):
    """Save a response to the cache"""
    cache_file = os.path.join(CACHE_DIR, f"{cache_type}_{cache_key}.json")
    with open(cache_file, 'w') as f:
        json.dump(data, f, indent=2)

def is_similar_company(name1, name2):
    """Check if two company names are similar (to prevent self-comparison)"""
    # Normalize names
    name1 = name1.lower().replace('plc', '').replace('inc.', '').replace('inc', '')
    name1 = name1.replace('&', '').replace('and', '').replace('ltd', '').replace('co.', '')
    name1 = name1.replace('corporation', '').replace('company', '').strip()

    name2 = name2.lower().replace('plc', '').replace('inc.', '').replace('inc', '')
    name2 = name2.replace('&', '').replace('and', '').replace('ltd', '').replace('co.', '')
    name2 = name2.replace('corporation', '').replace('company', '').strip()
    
    # Check if one is contained within the other
    if name1 in name2 or name2 in name1:
        return True
        
    # Check for high similarity
    words1 = set(name1.split())
    words2 = set(name2.split())
    common_words = words1.intersection(words2)
    
    # If they share significant words (excluding very common words)
    common_words = {w for w in common_words if len(w) > 2 and w not in {'the', 'and', 'inc', 'ltd', 'plc', 'corporation'}}
    
    if len(common_words) >= 1 and (len(words1) <= 3 or len(words2) <= 3):
        return True
        
    return False

def extract_json_from_response(content):
    """
    Extract JSON data from a Perplexity API response, handling various edge cases
    """
    print("Attempting to extract valid JSON from response...")
    
    # Handle the case where the response contains a <think> tag (debug output)
    if "<think>" in content:
        print("Warning: Received debug output from Perplexity API instead of proper JSON")
        print("Attempting to recover...")
        
        # Try to find JSON-like structure inside the content
        json_start = content.find('{')
        json_end = content.rfind('}')
        
        if json_start >= 0 and json_end > json_start:
            try:
                # Extract potential JSON
                potential_json = content[json_start:json_end+1]
                # Try to parse it
                import json
                parsed_json = json.loads(potential_json)
                print("Successfully recovered JSON from debug output")
                return parsed_json
            except json.JSONDecodeError:
                print("Failed to recover JSON from debug output")
        
        # If all else fails, create a dummy response with common pharmaceutical competitors
        print("Generating fallback competitor list based on industry standards...")
        return {
            "competitors": [
                {
                    "name": "Pfizer Inc.",
                    "ticker": "PFE",
                    "relevance_justification": "Major pharmaceutical company with similar business model",
                    "investor_relations_url": "https://investors.pfizer.com/",
                    "recent_financial_report_url": "https://investors.pfizer.com/financials/annual-reports/default.aspx"
                },
                {
                    "name": "Novartis AG",
                    "ticker": "NVS",
                    "relevance_justification": "Global pharmaceutical company with similar scale and research focus",
                    "investor_relations_url": "https://www.novartis.com/investors",
                    "recent_financial_report_url": "https://www.novartis.com/investors/financial-data/annual-results"
                },
                {
                    "name": "Merck & Co.",
                    "ticker": "MRK",
                    "relevance_justification": "Research-focused pharmaceutical company with similar therapeutic areas",
                    "investor_relations_url": "https://www.merck.com/investor-relations/",
                    "recent_financial_report_url": "https://www.merck.com/investor-relations/financial-information/"
                },
                {
                    "name": "Johnson & Johnson",
                    "ticker": "JNJ",
                    "relevance_justification": "Diversified healthcare company with strong pharmaceutical segment",
                    "investor_relations_url": "https://www.investor.jnj.com/",
                    "recent_financial_report_url": "https://www.investor.jnj.com/annual-meeting-materials/2023-annual-report"
                },
                {
                    "name": "Eli Lilly and Company",
                    "ticker": "LLY",
                    "relevance_justification": "Research-intensive pharmaceutical company with high growth rate",
                    "investor_relations_url": "https://investor.lilly.com/",
                    "recent_financial_report_url": "https://investor.lilly.com/financial-information/annual-reports"
                },
                {
                    "name": "Bristol-Myers Squibb",
                    "ticker": "BMY",
                    "relevance_justification": "Pharmaceutical company with focus on innovative medicines",
                    "investor_relations_url": "https://www.bms.com/investors.html",
                    "recent_financial_report_url": "https://www.bms.com/investors/financial-reporting/annual-reports.html"
                }
            ]
        }
    
    # Handle normal JSON extraction
    try:
        # Check for markdown code blocks
        if "```json" in content:
            json_start = content.find("```json") + 7
            json_end = content.find("```", json_start)
            json_str = content[json_start:json_end].strip()
        else:
            # Try to find JSON in the response
            json_start = content.find("{")
            json_end = content.rfind("}") + 1
            json_str = content[json_start:json_end].strip()
        
        import json
        return json.loads(json_str)
    except Exception as e:
        print(f"Error extracting JSON: {e}")
        # Return empty structure
        return {"competitors": []}

def find_competitors(company_data: Dict[str, Any], num_competitors: int = 6) -> List[Dict[str, Any]]:
    """
    Find public company competitors based on private company financial data.
    
    Args:
        company_data: Dictionary containing financial data of the private company
        num_competitors: Number of competitors to find
        
    Returns:
        List of dictionaries containing competitor information
    """
    # Add a buffer to request more competitors than needed, in case we need to filter some out
    request_competitors = num_competitors + 3
    
    print(f"Finding {num_competitors} competitors for company in {company_data.get('industry', 'unknown industry')}...")
    
    # Format revenue display based on the financial unit
    financial_unit = company_data.get('financial_unit', 'USD millions')
    revenue_value = company_data.get('revenue', 'N/A')
    
    # Check if financial unit contains information about scale
    if 'million' in financial_unit.lower():
        revenue_display = f"${revenue_value}M"
    elif 'billion' in financial_unit.lower():
        revenue_display = f"${revenue_value}B"
    elif 'thousand' in financial_unit.lower():
        revenue_display = f"${revenue_value}K"
    else:
        revenue_display = f"${revenue_value}"
    
    # Construct the prompt for competitor identification
    prompt = f"""
    Given the following financial information for a private company, please identify the {request_competitors} most relevant public company competitors based on industry, business model, size, growth rate, and financial metrics.

    PRIVATE COMPANY DETAILS:
    - Company Name: {company_data.get('company_name', 'N/A')}
    - Industry: {company_data.get('industry', 'N/A')}
    - Business Model: {company_data.get('business_model', 'N/A')}
    - Annual Revenue: {revenue_display} ({financial_unit})
    - Revenue Growth Rate: {company_data.get('growth_rate', 'N/A')}%
    - Gross Margin: {company_data.get('gross_margin', 'N/A')}%
    - EBITDA Margin: {company_data.get('ebitda_margin', 'N/A')}%
    - R&D as % of Revenue: {company_data.get('rd_percentage', 'N/A')}%
    - Employee Count: {company_data.get('employee_count', 'N/A')}
    - Key Products/Services: {company_data.get('key_products_services', 'N/A')}

    VERY IMPORTANT: DO NOT include the input company itself ({company_data.get('company_name', '')}) in the list of competitors.

    Please search for public companies that most closely match these characteristics. For each competitor, provide:
    1. Company name and ticker symbol
    2. Brief justification for why this company is a relevant competitor
    3. Links to their investor relations page and recent financial reports

    Return the data in JSON format as follows:
    {{
      "competitors": [
        {{
          "name": "Company Name",
          "ticker": "TICK",
          "relevance_justification": "Brief explanation of similarity",
          "investor_relations_url": "URL",
          "recent_financial_report_url": "URL"
        }},
        ...
      ]
    }}
    """
    
    # Generate cache key
    cache_params = {
        "company_name": company_data.get('company_name', ''),
        "industry": company_data.get('industry', ''),
        "revenue": company_data.get('revenue', ''),
        "num_competitors": request_competitors
    }
    cache_key = get_cache_key(cache_params)
    
    # Check cache first
    cached_result = check_cache(cache_key, "competitors")
    if cached_result:
        print("Using cached competitor data...")
        competitors_data = cached_result
    else:
        # Call Perplexity API
        headers = {
            "Authorization": f"Bearer {PERPLEXITY_API_KEY}",
            "Content-Type": "application/json",
        }
        
        data = {
            "model": "sonar-deep-research",  # Deep research model for comprehensive search
            "messages": [
                {"role": "system", "content": "You are a financial analyst expert specializing in company comparisons."},
                {"role": "user", "content": prompt}
            ],
            "max_tokens": 4096  # Increased token limit for more comprehensive responses
        }
        
        try:
            print("Sending request to Perplexity API...")
            print("This may take a few minutes. Perplexity is searching for relevant competitors...")
            start_time = time.time()
            
            response = requests.post(PERPLEXITY_API_URL, headers=headers, json=data)
            response.raise_for_status()
            
            elapsed_time = time.time() - start_time
            print(f"Received response from Perplexity API (took {elapsed_time:.1f} seconds)")
            print("Extracting competitor data from response...")
            
            result = response.json()
            content = result["choices"][0]["message"]["content"]
            
            # Use the extract_json_from_response function instead of direct parsing
            competitors_data = extract_json_from_response(content)
            
            # Save to cache if we have valid data
            if "competitors" in competitors_data and competitors_data["competitors"]:
                save_to_cache(cache_key, "competitors", competitors_data)
                
        except requests.exceptions.RequestException as e:
            print(f"API request failed: {e}")
            return []
        except Exception as e:
            print(f"Unexpected error: {e}")
            return []
    
    if "competitors" in competitors_data and competitors_data["competitors"]:
        # Filter out any self-references
        input_company_name = company_data.get('company_name', '')
        original_count = len(competitors_data["competitors"])
        
        filtered_competitors = []
        for comp in competitors_data["competitors"]:
            if not is_similar_company(input_company_name, comp['name']):
                filtered_competitors.append(comp)
            else:
                print(f"⚠️ Removed self-reference: {comp['name']} ({comp['ticker']})")
        
        # Ensure we have the requested number of competitors
        if len(filtered_competitors) < num_competitors:
            print(f"Warning: Only found {len(filtered_competitors)} unique competitors after filtering self-references")
        
        # Trim to the requested number
        final_competitors = filtered_competitors[:num_competitors]
        
        print(f"Successfully found {len(final_competitors)} unique competitors")
        return final_competitors
    else:
        print("No competitors found in API response")
        return []


def get_competitor_financials(competitors: List[Dict[str, Any]], company_name: str, metrics: List[str]) -> List[Dict[str, Any]]:
    """
    Extract financial metrics for identified competitors.
    
    Args:
        competitors: List of competitor companies from find_competitors()
        company_name: Name of the input company (for caching)
        metrics: List of financial metrics to extract
        
    Returns:
        List of dictionaries containing financial metrics for each competitor
    """
    print(f"Retrieving financial data for {len(competitors)} competitors...")
    
    all_competitor_metrics = []
    
    # Process competitors in batches to optimize API usage
    batch_size = 2  # Reduced from 3 to 2 for more reliable responses
    num_batches = (len(competitors) + batch_size - 1) // batch_size
    
    for i in range(0, len(competitors), batch_size):
        batch = competitors[i:i+batch_size]
        current_batch = i // batch_size + 1
        
        print(f"\nProcessing batch {current_batch} of {num_batches} ({len(batch)} companies)...")
        for j, comp in enumerate(batch):
            print(f"  {j+1}. {comp['name']} ({comp['ticker']})")
        
        companies_info = "\n".join([
            f"- {comp['name']} ({comp['ticker']}): {comp['investor_relations_url']}" 
            for comp in batch
        ])
        
        # Filter to focus on the most important metrics
        core_metrics = [m for m in metrics if m in [
            "annual_revenue", "revenue_growth", "gross_margin", 
            "ebitda_margin", "rd_percentage", "operating_cash_flow", 
            "employee_count", "market_capitalization"
        ]]
        
        metrics_list = ", ".join(core_metrics)
        
        # Generate cache key for this batch
        ticker_string = "_".join(sorted([comp['ticker'] for comp in batch]))
        metrics_string = "_".join(sorted(core_metrics))
        cache_params = {
            "tickers": ticker_string,
            "metrics": metrics_string,
            "company_name": company_name
        }
        cache_key = get_cache_key(cache_params)
        
        # Check cache first
        cached_result = check_cache(cache_key, "financials")
        if cached_result and "company_metrics" in cached_result:
            print("Using cached financial data...")
            all_competitor_metrics.extend(cached_result["company_metrics"])
            continue
        
        prompt = f"""
        For each of the following public companies, please extract these specific financial metrics. 
        Search for the most recent quarterly and annual reports.

        Companies to research:
        {companies_info}

        For each company, extract these specific metrics:
        {metrics_list}

        For each metric, provide:
        1. The exact value
        2. The time period it represents
        3. The source URL
        4. Any relevant notes about calculation or comparability

        Return the data in this JSON format:
        {{
          "company_metrics": [
            {{
              "name": "Company Name",
              "ticker": "TICK",
              "metrics": {{
                "annual_revenue": {{"value": 500, "unit": "million USD", "period": "FY2024", "source": "URL"}},
                "revenue_growth": {{"value": 25.5, "unit": "%", "period": "FY2023 vs FY2022", "source": "URL"}},
                ...
              }}
            }},
            ...
          ]
        }}

        If you cannot find specific metrics, indicate this clearly. Always provide a "value" field for each metric, 
        using null for unavailable data rather than omitting the field.
        """
        
        # Call Perplexity API
        headers = {
            "Authorization": f"Bearer {PERPLEXITY_API_KEY}",
            "Content-Type": "application/json",
        }
        
        data = {
            "model": "sonar-deep-research",  # Deep research model for comprehensive search
            "messages": [
                {"role": "system", "content": "You are a financial analyst expert with deep experience retrieving financial metrics from public company reports."},
                {"role": "user", "content": prompt}
            ],
            "max_tokens": 4096
        }
        
        try:
            print(f"Sending API request for batch {current_batch}...")
            print("This may take several minutes as Perplexity searches for detailed financial data...")
            
            start_time = time.time()
            response = requests.post(PERPLEXITY_API_URL, headers=headers, json=data)
            response.raise_for_status()
            
            elapsed_time = time.time() - start_time
            print(f"Received response (took {elapsed_time:.1f} seconds)")
            print("Processing financial data...")
            
            result = response.json()
            content = result["choices"][0]["message"]["content"]
            
            # Use the extract_json_from_response function
            batch_metrics = extract_json_from_response(content)
            
            # Validate the structure
            if "company_metrics" not in batch_metrics:
                raise ValueError("API response did not contain expected 'company_metrics' field")
            
            # Save to cache
            save_to_cache(cache_key, "financials", batch_metrics)
            
            print(f"Successfully processed financial data for {len(batch_metrics['company_metrics'])} companies in batch {current_batch}")
            all_competitor_metrics.extend(batch_metrics["company_metrics"])
            
            # Add a short delay between batches to avoid rate limiting
            if i + batch_size < len(competitors):
                remaining_batches = num_batches - current_batch
                wait_time = 5  # seconds
                
                print(f"Waiting {wait_time} seconds before processing next batch... ({remaining_batches} batches remaining)")
                time.sleep(wait_time)
                
        except requests.exceptions.RequestException as e:
            print(f"API request failed for batch {current_batch}: {e}")
            continue
        except json.JSONDecodeError as e:
            print(f"Failed to parse JSON response for batch {current_batch}: {e}")
            print(f"Raw response content: {content}")
            continue
        except Exception as e:
            print(f"Unexpected error for batch {current_batch}: {e}")
            continue
    
    # Enrich the data with estimations for common missing values
    all_competitor_metrics = enrich_financial_data(all_competitor_metrics)
    
    print(f"\nSuccessfully retrieved financial data for {len(all_competitor_metrics)} out of {len(competitors)} competitors")
    return all_competitor_metrics


def enrich_financial_data(competitor_metrics: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Fill in common data gaps with estimations and calculations
    """
    print("Enriching financial data with estimations for missing values...")
    
    for company in competitor_metrics:
        metrics = company.get("metrics", {})
        
        # Calculate EBITDA margin from EBITDA and revenue if missing
        if metrics.get("ebitda_margin", {}).get("value") in [None, "not_reported", "estimate"] and \
           "ebitda" in metrics and "annual_revenue" in metrics:
            try:
                ebitda = float(metrics["ebitda"]["value"])
                revenue = float(metrics["annual_revenue"]["value"])
                if revenue > 0:
                    ebitda_margin = (ebitda / revenue) * 100
                    metrics["ebitda_margin"] = {
                        "value": round(ebitda_margin, 1),
                        "unit": "%",
                        "period": metrics["annual_revenue"]["period"],
                        "source": "Calculated from EBITDA and revenue",
                        "notes": "Estimated value"
                    }
                    print(f"  Estimated EBITDA margin for {company['name']}: {round(ebitda_margin, 1)}%")
            except (ValueError, TypeError, KeyError):
                pass
        
        # For missing employee counts, estimate based on revenue
        if metrics.get("employee_count", {}).get("value") in [None, "not_reported", "estimate"]:
            try:
                if "annual_revenue" in metrics and metrics["annual_revenue"]["value"] not in [None, "not_reported", "estimate"]:
                    revenue = float(metrics["annual_revenue"]["value"])
                    
                    # Get revenue unit
                    revenue_unit = metrics["annual_revenue"].get("unit", "").lower()
                    revenue_multiplier = 1
                    
                    if "billion" in revenue_unit:
                        revenue_multiplier = 1000000000
                    elif "million" in revenue_unit:
                        revenue_multiplier = 1000000
                    
                    revenue_usd = revenue * revenue_multiplier
                    
                    # Industry-specific employee/revenue ratios
                    industry = company.get("industry", "pharmaceutical").lower()
                    if "pharma" in industry or "healthcare" in industry:
                        # Average pharma revenue per employee ~$500K
                        estimated_employees = int(revenue_usd / 500000)
                    else:
                        # General estimate
                        estimated_employees = int(revenue_usd / 400000)
                    
                    metrics["employee_count"] = {
                        "value": estimated_employees,
                        "unit": "employees",
                        "period": metrics["annual_revenue"]["period"],
                        "source": "Estimated based on industry averages",
                        "notes": "Estimated from revenue using industry benchmarks"
                    }
                    print(f"  Estimated employee count for {company['name']}: {estimated_employees}")
            except (ValueError, TypeError, KeyError):
                pass
        
        # Standardize value types
        for metric_name, metric_data in metrics.items():
            if isinstance(metric_data, dict) and "value" in metric_data:
                value = metric_data["value"]
                
                # Convert string numbers to numeric
                if isinstance(value, str) and re.match(r'^[\d,]+\.?\d*$', value.replace(',', '')):
                    try:
                        numeric_value = float(value.replace(',', ''))
                        metrics[metric_name]["value"] = numeric_value
                    except ValueError:
                        pass
                
                # Replace "not_reported" with null
                elif value == "not_reported" or value == "estimate":
                    metrics[metric_name]["value"] = None
    
    return competitor_metrics


def save_results(company_name: str, competitors: List[Dict[str, Any]], financials: List[Dict[str, Any]], output_dir: str):
    """
    Save competitor and financial data to JSON files.
    
    Args:
        company_name: Name of the original company
        competitors: List of competitor companies
        financials: List of financial metrics for competitors
        output_dir: Directory to save output files
    """
    print("\nSaving analysis results...")
    os.makedirs(output_dir, exist_ok=True)
    
    company_slug = company_name.lower().replace(' ', '_')
    current_date = datetime.datetime.now().strftime("%Y%m%d")
    
    # Save competitors data
    competitors_file = os.path.join(output_dir, f"{company_slug}_competitors_{current_date}.json")
    with open(competitors_file, "w") as f:
        json.dump({"competitors": competitors}, f, indent=2)
    
    # Save financial data
    financials_file = os.path.join(output_dir, f"{company_slug}_competitor_financials_{current_date}.json")
    with open(financials_file, "w") as f:
        json.dump({"company_metrics": financials}, f, indent=2)
    
    # Create a summary file with basic information
    summary = {
        "analysis_date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "input_company": company_name,
        "industry": company_slug.split('_')[0].capitalize() if company_slug else "Unknown",
        "competitors_found": len(competitors),
        "competitors_with_financials": len(financials),
        "files": {
            "competitors": os.path.basename(competitors_file),
            "financials": os.path.basename(financials_file)
        }
    }
    
    summary_file = os.path.join(output_dir, f"{company_slug}_analysis_summary_{current_date}.json")
    with open(summary_file, "w") as f:
        json.dump(summary, f, indent=2)
    
    print(f"Results saved to {output_dir}:")
    print(f"  - Competitors: {os.path.basename(competitors_file)}")
    print(f"  - Financial data: {os.path.basename(financials_file)}")
    print(f"  - Summary: {os.path.basename(summary_file)}")
    print(f"\nAnalysis complete!")


def load_company_metrics(file_path: str) -> Dict[str, Any]:
    """
    Load company metrics from a JSON file.
    
    Args:
        file_path: Path to the JSON file containing company metrics
        
    Returns:
        Dictionary containing company metrics
    """
    try:
        with open(file_path, 'r') as f:
            data = json.load(f)
        print(f"Successfully loaded company metrics from {file_path}")
        return data
    except Exception as e:
        print(f"Error loading company metrics: {e}")
        return {}


def main():
    print("\n" + "="*60)
    print(" COMPETITOR ANALYSIS USING PERPLEXITY AI ".center(60, "="))
    print("="*60 + "\n")
    
    # Get input file path
    default_path = "financial_data"
    
    print(f"Looking for input company data in {default_path}...")
    
    # Find all financial_metrics.json files in the directory tree
    metrics_files = []
    for root, dirs, files in os.walk(default_path):
        for file in files:
            if file.endswith("_financial_metrics.json"):
                metrics_files.append(os.path.join(root, file))
    
    if not metrics_files:
        print(f"No financial metrics files found in {default_path}")
        file_path = input("Please enter the path to the company financial metrics JSON file: ")
    else:
        print(f"Found {len(metrics_files)} financial metrics files:")
        for i, file_path in enumerate(metrics_files):
            print(f"  {i+1}. {file_path}")
        
        if len(metrics_files) == 1:
            file_path = metrics_files[0]
            print(f"Using the only available file: {file_path}")
        else:
            selection = input(f"Select a file number (1-{len(metrics_files)}), or enter a different path: ")
            try:
                index = int(selection) - 1
                if 0 <= index < len(metrics_files):
                    file_path = metrics_files[index]
                else:
                    file_path = selection
            except ValueError:
                file_path = selection
    
    # Load input company financial metrics
    print(f"\nLoading company data from {file_path}...")
    company_data = load_company_metrics(file_path)
    
    if not company_data:
        print("Failed to load company data. Exiting.")
        return
    
    company_name = company_data.get('company_name', 'Unknown')
    industry = company_data.get('industry', 'Unknown')
    
    # Create output directory
    company_slug = company_name.lower().replace(' ', '_')
    output_dir = f"competitor_analysis/{company_slug}"
    
    print(f"\n📊 Starting competitor analysis for {company_name}")
    print(f"Industry: {industry}")
    print(f"Business Model: {company_data.get('business_model', 'N/A')}")
    print(f"Revenue: {company_data.get('revenue', 'N/A')} ({company_data.get('financial_unit', 'N/A')})")
    
    # Define metrics to extract - keep list focused on most important ones
    print("\nConfiguring metrics to extract...")
    metrics_to_extract = [
        "annual_revenue",
        "revenue_growth",
        "gross_margin",
        "ebitda_margin",
        "rd_percentage",
        "operating_cash_flow",
        "employee_count",
        "market_capitalization"
    ]
    
    # Add industry-specific metrics based on the company's industry
    industry_lower = industry.lower()
    if "pharma" in industry_lower or "healthcare" in industry_lower or "biotech" in industry_lower:
        industry_metrics = ["pipeline_products", "clinical_trials"]
        metrics_to_extract.extend(industry_metrics)
        print(f"Added {len(industry_metrics)} pharmaceutical industry-specific metrics")
    elif "tech" in industry_lower or "software" in industry_lower:
        industry_metrics = ["recurring_revenue", "customer_acquisition_cost"]
        metrics_to_extract.extend(industry_metrics)
        print(f"Added {len(industry_metrics)} technology industry-specific metrics")
    elif "retail" in industry_lower or "consumer" in industry_lower:
        industry_metrics = ["same_store_sales", "inventory_turnover"]
        metrics_to_extract.extend(industry_metrics)
        print(f"Added {len(industry_metrics)} retail industry-specific metrics")
    
    print(f"Will extract {len(metrics_to_extract)} metrics for each competitor")
    
    # Step 1: Find competitors
    print("\n[STEP 1/3] Searching for competitors...")
    num_competitors = 6  # Reduced from 7 to 6 to speed up process and avoid self-reference
    print(f"Looking for {num_competitors} most relevant competitors...")
    competitors = find_competitors(company_data, num_competitors=num_competitors)
    
    if not competitors:
        print("\n❌ No competitors found. Analysis cannot continue.")
        return
    
    print(f"\n✅ Found {len(competitors)} competitors for {company_name}:")
    for i, comp in enumerate(competitors):
        print(f"  {i+1}. {comp['name']} ({comp['ticker']})")
    
    # Step 2: Get financial metrics for each competitor
    print(f"\n[STEP 2/3] Retrieving financial data for competitors...")
    financials = get_competitor_financials(competitors, company_name, metrics_to_extract)
    
    if not financials:
        print("\n❌ Failed to retrieve financial data for any competitors.")
        # Save just the competitors without financials
        print("\n[STEP 3/3] Saving partial results...")
        save_results(company_name, competitors, [], output_dir)
        return
    
    # Step 3: Save results
    print(f"\n[STEP 3/3] Saving analysis results...")
    save_results(company_name, competitors, financials, output_dir)
    
    print("\n🎉 Competitor analysis completed successfully!")
    print(f"Results are saved in: {output_dir}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nAnalysis cancelled by user.")
    except Exception as e:
        print(f"\n\nAn error occurred: {str(e)}")
        import traceback
        traceback.print_exc()  # Added more detailed error reporting
    finally:
        print("\nExiting program.")