import os
import json
import requests
import time
import datetime
import re
import hashlib
import argparse
from dotenv import load_dotenv
from typing import Dict, List, Optional, Any
from concurrent.futures import ThreadPoolExecutor, as_completed

# Set up argument parsing
parser = argparse.ArgumentParser(description='Competitor research using Perplexity API')
parser.add_argument('-f', '--file', help='Path to the financial metrics JSON file')
parser.add_argument('--industry', help='Override the industry for competitor search')
parser.add_argument('--competitors', type=int, default=6, help='Number of competitors to find (default: 6)')
parser.add_argument('--output-dir', help='Custom output directory for results')
args = parser.parse_args()

# Load environment variables
load_dotenv()

# Get API keys
PERPLEXITY_API_KEY = os.getenv("PERPLEXITY_API_KEY")
ALPHA_VANTAGE_API_KEY = os.getenv("ALPHA_VANTAGE_API_KEY")
FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY")

if not PERPLEXITY_API_KEY:
    raise ValueError("PERPLEXITY_API_KEY not found in environment variables")
if not ALPHA_VANTAGE_API_KEY:
    print("Warning: ALPHA_VANTAGE_API_KEY not found in environment variables")
if not FINNHUB_API_KEY:
    print("Warning: FINNHUB_API_KEY not found in environment variables")

# API endpoints
PERPLEXITY_API_URL = "https://api.perplexity.ai/chat/completions"
ALPHA_VANTAGE_BASE_URL = "https://www.alphavantage.co/query"
FINNHUB_BASE_URL = "https://finnhub.io/api/v1"

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

def generate_fallback_competitors(industry):
    """
    Generate a fallback list of competitors based on the company's industry.
    This is used when the API fails to return proper results.
    """
    print(f"Generating fallback competitor list based on {industry} industry standards...")
    
    # Normalize industry name to match our categories
    industry_lower = industry.lower()
    
    # Pharmaceutical/Healthcare fallbacks
    if any(term in industry_lower for term in ["pharma", "drug", "healthcare", "biotech", "medical"]):
        return {
            "competitors": [
                {
                    "name": "Pfizer Inc.",
                    "ticker": "PFE",
                    "relevance_justification": "Major pharmaceutical company with diverse portfolio",
                    "investor_relations_url": "https://investors.pfizer.com/",
                    "recent_financial_report_url": "https://investors.pfizer.com/financials/annual-reports/default.aspx"
                },
                {
                    "name": "Novartis AG",
                    "ticker": "NVS",
                    "relevance_justification": "Global pharmaceutical company with research focus",
                    "investor_relations_url": "https://www.novartis.com/investors",
                    "recent_financial_report_url": "https://www.novartis.com/investors/financial-data/annual-results"
                },
                {
                    "name": "Merck & Co.",
                    "ticker": "MRK",
                    "relevance_justification": "Research-focused pharmaceutical company",
                    "investor_relations_url": "https://www.merck.com/investor-relations/",
                    "recent_financial_report_url": "https://www.merck.com/investor-relations/financial-information/"
                },
                {
                    "name": "Johnson & Johnson",
                    "ticker": "JNJ",
                    "relevance_justification": "Diversified healthcare company",
                    "investor_relations_url": "https://www.investor.jnj.com/",
                    "recent_financial_report_url": "https://www.investor.jnj.com/annual-meeting-materials/2023-annual-report"
                },
                {
                    "name": "Eli Lilly and Company",
                    "ticker": "LLY",
                    "relevance_justification": "Research-intensive pharmaceutical company",
                    "investor_relations_url": "https://investor.lilly.com/",
                    "recent_financial_report_url": "https://investor.lilly.com/financial-information/annual-reports"
                },
                {
                    "name": "Bristol-Myers Squibb",
                    "ticker": "BMY",
                    "relevance_justification": "Pharmaceutical company with innovative focus",
                    "investor_relations_url": "https://www.bms.com/investors.html",
                    "recent_financial_report_url": "https://www.bms.com/investors/financial-reporting/annual-reports.html"
                }
            ]
        }
    
    # Technology fallbacks
    elif any(term in industry_lower for term in ["tech", "software", "IT", "digital", "computer", "saas"]):
        return {
            "competitors": [
                {
                    "name": "Microsoft Corporation",
                    "ticker": "MSFT",
                    "relevance_justification": "Major technology company with diverse software offerings",
                    "investor_relations_url": "https://www.microsoft.com/en-us/investor",
                    "recent_financial_report_url": "https://www.microsoft.com/en-us/investor/earnings/fy-2023-q4/press-release-webcast"
                },
                {
                    "name": "Oracle Corporation",
                    "ticker": "ORCL",
                    "relevance_justification": "Enterprise software and cloud computing company",
                    "investor_relations_url": "https://investor.oracle.com/",
                    "recent_financial_report_url": "https://investor.oracle.com/quarterly-results/default.aspx"
                },
                {
                    "name": "SAP SE",
                    "ticker": "SAP",
                    "relevance_justification": "Enterprise software and business solutions",
                    "investor_relations_url": "https://www.sap.com/investors/en.html",
                    "recent_financial_report_url": "https://www.sap.com/investors/en/reports.html"
                },
                {
                    "name": "Salesforce, Inc.",
                    "ticker": "CRM",
                    "relevance_justification": "CRM and cloud computing solutions",
                    "investor_relations_url": "https://investor.salesforce.com/",
                    "recent_financial_report_url": "https://investor.salesforce.com/financials/default.aspx"
                },
                {
                    "name": "Adobe Inc.",
                    "ticker": "ADBE",
                    "relevance_justification": "Software and creative solutions provider",
                    "investor_relations_url": "https://www.adobe.com/investor-relations.html",
                    "recent_financial_report_url": "https://www.adobe.com/investor-relations/financial-documents.html"
                },
                {
                    "name": "IBM Corporation",
                    "ticker": "IBM",
                    "relevance_justification": "Technology and consulting services",
                    "investor_relations_url": "https://www.ibm.com/investor",
                    "recent_financial_report_url": "https://www.ibm.com/investor/financials/financial-reporting"
                }
            ]
        }
    
    # Financial Services fallbacks
    elif any(term in industry_lower for term in ["bank", "finance", "insurance", "invest", "capital"]):
        return {
            "competitors": [
                {
                    "name": "JPMorgan Chase & Co.",
                    "ticker": "JPM",
                    "relevance_justification": "Major financial services company",
                    "investor_relations_url": "https://www.jpmorganchase.com/ir",
                    "recent_financial_report_url": "https://www.jpmorganchase.com/ir/quarterly-earnings"
                },
                {
                    "name": "Bank of America Corporation",
                    "ticker": "BAC",
                    "relevance_justification": "Global banking and financial services",
                    "investor_relations_url": "https://investor.bankofamerica.com/",
                    "recent_financial_report_url": "https://investor.bankofamerica.com/quarterly-earnings"
                },
                {
                    "name": "Citigroup Inc.",
                    "ticker": "C",
                    "relevance_justification": "Multinational investment bank",
                    "investor_relations_url": "https://www.citigroup.com/global/investors",
                    "recent_financial_report_url": "https://www.citigroup.com/global/investors/quarterly-earnings"
                },
                {
                    "name": "Wells Fargo & Company",
                    "ticker": "WFC",
                    "relevance_justification": "Financial services company",
                    "investor_relations_url": "https://www.wellsfargo.com/about/investor-relations/",
                    "recent_financial_report_url": "https://www.wellsfargo.com/about/investor-relations/quarterly-earnings/"
                },
                {
                    "name": "The Goldman Sachs Group, Inc.",
                    "ticker": "GS",
                    "relevance_justification": "Investment banking and financial services",
                    "investor_relations_url": "https://www.goldmansachs.com/investor-relations/",
                    "recent_financial_report_url": "https://www.goldmansachs.com/investor-relations/financials/"
                },
                {
                    "name": "Morgan Stanley",
                    "ticker": "MS",
                    "relevance_justification": "Investment management and financial services",
                    "investor_relations_url": "https://www.morganstanley.com/about-us-ir",
                    "recent_financial_report_url": "https://www.morganstanley.com/about-us-ir/earnings-releases"
                }
            ]
        }
    
    # Retail fallbacks
    elif any(term in industry_lower for term in ["retail", "consumer", "ecommerce", "store"]):
        return {
            "competitors": [
                {
                    "name": "Walmart Inc.",
                    "ticker": "WMT",
                    "relevance_justification": "Major retail corporation",
                    "investor_relations_url": "https://corporate.walmart.com/investors",
                    "recent_financial_report_url": "https://corporate.walmart.com/investors/financial-information/quarterly-results"
                },
                {
                    "name": "Target Corporation",
                    "ticker": "TGT",
                    "relevance_justification": "Retail store chain",
                    "investor_relations_url": "https://investors.target.com/",
                    "recent_financial_report_url": "https://investors.target.com/financial-information/quarterly-results"
                },
                {
                    "name": "Costco Wholesale Corporation",
                    "ticker": "COST",
                    "relevance_justification": "Membership warehouse retailer",
                    "investor_relations_url": "https://investor.costco.com/",
                    "recent_financial_report_url": "https://investor.costco.com/financial-information/quarterly-results"
                },
                {
                    "name": "The Home Depot, Inc.",
                    "ticker": "HD",
                    "relevance_justification": "Home improvement retailer",
                    "investor_relations_url": "https://ir.homedepot.com/",
                    "recent_financial_report_url": "https://ir.homedepot.com/financial-reports/quarterly-earnings"
                },
                {
                    "name": "The Kroger Co.",
                    "ticker": "KR",
                    "relevance_justification": "Supermarket chain",
                    "investor_relations_url": "https://ir.kroger.com/",
                    "recent_financial_report_url": "https://ir.kroger.com/financials/quarterly-results/default.aspx"
                },
                {
                    "name": "Lowe's Companies, Inc.",
                    "ticker": "LOW",
                    "relevance_justification": "Home improvement retailer",
                    "investor_relations_url": "https://corporate.lowes.com/investors",
                    "recent_financial_report_url": "https://corporate.lowes.com/investors/financial-information/quarterly-earnings"
                }
            ]
        }
    
    # Energy fallbacks
    elif any(term in industry_lower for term in ["energy", "oil", "gas", "renewable", "power", "utility"]):
        return {
            "competitors": [
                {
                    "name": "Exxon Mobil Corporation",
                    "ticker": "XOM",
                    "relevance_justification": "Major oil and gas company",
                    "investor_relations_url": "https://corporate.exxonmobil.com/investors",
                    "recent_financial_report_url": "https://corporate.exxonmobil.com/investors/financial-reporting"
                },
                {
                    "name": "Chevron Corporation",
                    "ticker": "CVX",
                    "relevance_justification": "Multinational energy corporation",
                    "investor_relations_url": "https://www.chevron.com/investors",
                    "recent_financial_report_url": "https://www.chevron.com/investors/quarterly-results"
                },
                {
                    "name": "Shell plc",
                    "ticker": "SHEL",
                    "relevance_justification": "Global energy and petrochemical company",
                    "investor_relations_url": "https://www.shell.com/investors.html",
                    "recent_financial_report_url": "https://www.shell.com/investors/results-and-reporting.html"
                },
                {
                    "name": "BP p.l.c.",
                    "ticker": "BP",
                    "relevance_justification": "Oil and gas company",
                    "investor_relations_url": "https://www.bp.com/en/global/corporate/investors.html",
                    "recent_financial_report_url": "https://www.bp.com/en/global/corporate/investors/results-and-reporting.html"
                },
                {
                    "name": "TotalEnergies SE",
                    "ticker": "TTE",
                    "relevance_justification": "Multinational energy company",
                    "investor_relations_url": "https://totalenergies.com/investors",
                    "recent_financial_report_url": "https://totalenergies.com/investors/publications-and-regulated-information/regulated-information/annual-and-quarterly"
                },
                {
                    "name": "ConocoPhillips",
                    "ticker": "COP",
                    "relevance_justification": "Exploration and production company",
                    "investor_relations_url": "https://www.conocophillips.com/investor-relations/",
                    "recent_financial_report_url": "https://www.conocophillips.com/investor-relations/financial-information/"
                }
            ]
        }
        
    # Generic fallback for other industries
    else:
        return {
            "competitors": [
                {
                    "name": "Company 1 Inc.",
                    "ticker": "SYMB1",
                    "relevance_justification": f"Major player in the {industry} industry",
                    "investor_relations_url": "https://example.com/investors",
                    "recent_financial_report_url": "https://example.com/financials"
                },
                {
                    "name": "Company 2 Corp.",
                    "ticker": "SYMB2",
                    "relevance_justification": f"Leading {industry} company with similar business model",
                    "investor_relations_url": "https://example2.com/investors",
                    "recent_financial_report_url": "https://example2.com/financials"
                },
                {
                    "name": "Company 3 Ltd.",
                    "ticker": "SYMB3",
                    "relevance_justification": f"Established {industry} business with global presence",
                    "investor_relations_url": "https://example3.com/investors",
                    "recent_financial_report_url": "https://example3.com/financials"
                },
                {
                    "name": "Company 4 LLC",
                    "ticker": "SYMB4",
                    "relevance_justification": f"Fast-growing competitor in the {industry} space",
                    "investor_relations_url": "https://example4.com/investors",
                    "recent_financial_report_url": "https://example4.com/financials"
                },
                {
                    "name": "Company 5 Group",
                    "ticker": "SYMB5",
                    "relevance_justification": f"Innovative {industry} company with diverse portfolio",
                    "investor_relations_url": "https://example5.com/investors",
                    "recent_financial_report_url": "https://example5.com/financials"
                },
                {
                    "name": "Company 6 Enterprises",
                    "ticker": "SYMB6",
                    "relevance_justification": f"Established player in the {industry} industry",
                    "investor_relations_url": "https://example6.com/investors",
                    "recent_financial_report_url": "https://example6.com/financials"
                }
            ]
        }
    

def extract_json_from_response(content, industry):
    """
    Extract JSON data from a Perplexity API response, handling various edge cases
    
    Args:
        content: API response content
        industry: Industry of the input company (for fallback generation)
    
    Returns:
        Parsed JSON data
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
        
        # If all else fails, create industry-specific fallback competitors
        return generate_fallback_competitors(industry)
    
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
        # Return industry-specific fallback
        return generate_fallback_competitors(industry)

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
    
    # Get industry for potential fallback generation
    industry = company_data.get('industry', 'Unknown')
    
    print(f"Finding {num_competitors} competitors for company in {industry}...")
    
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
    - Industry: {industry}
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

    VERY IMPORTANT: Ensure the ticker symbol is accurate and corresponds to the actual trading symbol on major exchanges like NYSE or NASDAQ. This is critical for subsequent financial data retrieval.

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
        "industry": industry,
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
            competitors_data = extract_json_from_response(content, industry)
            
            # Save to cache if we have valid data
            if "competitors" in competitors_data and competitors_data["competitors"]:
                save_to_cache(cache_key, "competitors", competitors_data)
                
        except requests.exceptions.RequestException as e:
            print(f"API request failed: {e}")
            competitors_data = generate_fallback_competitors(industry)
        except Exception as e:
            print(f"Unexpected error: {e}")
            competitors_data = generate_fallback_competitors(industry)
    
    if "competitors" in competitors_data and competitors_data["competitors"]:
        # Filter out any self-references
        input_company_name = company_data.get('company_name', '')
        original_count = len(competitors_data["competitors"])
        
        filtered_competitors = []
        for comp in competitors_data["competitors"]:
            if not is_similar_company(input_company_name, comp['name']):
                filtered_competitors.append(comp)
            else:
                print(f"Removed self-reference: {comp['name']} ({comp['ticker']})")
        
        # Ensure we have the requested number of competitors
        if len(filtered_competitors) < num_competitors:
            print(f"Warning: Only found {len(filtered_competitors)} unique competitors after filtering self-references")
            
            # If we have too few competitors after filtering, add some from the industry fallbacks
            if len(filtered_competitors) < num_competitors // 2:
                fallback_competitors = generate_fallback_competitors(industry)["competitors"]
                
                # Add fallbacks that aren't already in our list
                existing_tickers = {comp['ticker'] for comp in filtered_competitors}
                for comp in fallback_competitors:
                    if comp['ticker'] not in existing_tickers and not is_similar_company(input_company_name, comp['name']):
                        filtered_competitors.append(comp)
                        existing_tickers.add(comp['ticker'])
                        if len(filtered_competitors) >= num_competitors:
                            break
        
        # Trim to the requested number
        final_competitors = filtered_competitors[:num_competitors]
        
        print(f"Successfully found {len(final_competitors)} unique competitors")
        return final_competitors
    else:
        print("No competitors found in API response")
        return []

def get_alpha_vantage_financials(ticker: str) -> Dict:
    """
    Retrieve financial metrics from Alpha Vantage API
    
    Args:
        ticker: Company ticker symbol
        
    Returns:
        Dictionary containing financial metrics
    """
    if not ALPHA_VANTAGE_API_KEY:
        return None
    
    print(f"Retrieving Alpha Vantage data for {ticker}...")
    
    # Generate cache key
    cache_key = f"alphavantage_{ticker}"
    
    # Check cache first
    cached_result = check_cache(cache_key, "financials")
    if cached_result:
        print(f"Using cached Alpha Vantage data for {ticker}")
        return cached_result
    
    # Define the metrics to retrieve
    metrics = {}
    
    try:
        # 1. Get Overview (for general company information)
        overview_params = {
            "function": "OVERVIEW",
            "symbol": ticker,
            "apikey": ALPHA_VANTAGE_API_KEY
        }
        
        overview_response = requests.get(ALPHA_VANTAGE_BASE_URL, params=overview_params)
        overview_data = overview_response.json()
        
        if "Symbol" in overview_data:
            # Extract key metrics from overview
            metrics["market_capitalization"] = {
                "value": float(overview_data.get("MarketCapitalization", 0)) / 1000000,  # Convert to millions
                "unit": "million USD",
                "period": "Latest",
                "source": "Alpha Vantage OVERVIEW",
                "notes": "Market capitalization in millions USD"
            }
            
            metrics["employee_count"] = {
                "value": int(overview_data.get("FullTimeEmployees", 0)) if overview_data.get("FullTimeEmployees") else None,
                "unit": "employees",
                "period": "Latest",
                "source": "Alpha Vantage OVERVIEW",
                "notes": "Full-time employee count"
            }
            
            if "PERatio" in overview_data and overview_data["PERatio"] != "None":
                metrics["price_to_earnings_ratio"] = {
                    "value": float(overview_data.get("PERatio", 0)),
                    "unit": "ratio",
                    "period": "Latest",
                    "source": "Alpha Vantage OVERVIEW",
                    "notes": "Price to earnings ratio"
                }
            
            if "ProfitMargin" in overview_data and overview_data["ProfitMargin"] != "None":
                profit_margin = float(overview_data.get("ProfitMargin", 0)) * 100  # Convert to percentage
                metrics["ebitda_margin"] = {
                    "value": profit_margin,
                    "unit": "%",
                    "period": "Latest",
                    "source": "Alpha Vantage OVERVIEW",
                    "notes": "Using profit margin as an approximation for EBITDA margin"
                }
        
        # 2. Get Income Statement (for revenue, growth, margins)
        time.sleep(0.5)  # To avoid API rate limiting
        income_params = {
            "function": "INCOME_STATEMENT",
            "symbol": ticker,
            "apikey": ALPHA_VANTAGE_API_KEY
        }
        
        income_response = requests.get(ALPHA_VANTAGE_BASE_URL, params=income_params)
        income_data = income_response.json()
        
        if "annualReports" in income_data and len(income_data["annualReports"]) > 0:
            annual_reports = income_data["annualReports"]
            
            # Get the most recent fiscal year
            most_recent = annual_reports[0]
            fiscal_year = most_recent.get("fiscalDateEnding", "")
            
            # Extract revenue
            if "totalRevenue" in most_recent and most_recent["totalRevenue"] != "None":
                revenue = float(most_recent["totalRevenue"]) / 1000000  # Convert to millions
                metrics["annual_revenue"] = {
                    "value": revenue,
                    "unit": "million USD",
                    "period": fiscal_year,
                    "source": "Alpha Vantage INCOME_STATEMENT",
                    "notes": "Annual revenue from income statement"
                }
            
            # Calculate revenue growth if we have enough data
            if len(annual_reports) > 1 and "totalRevenue" in annual_reports[1] and annual_reports[1]["totalRevenue"] != "None":
                current_revenue = float(most_recent["totalRevenue"])
                previous_revenue = float(annual_reports[1]["totalRevenue"])
                
                if previous_revenue > 0:
                    growth_rate = ((current_revenue - previous_revenue) / previous_revenue) * 100
                    metrics["revenue_growth"] = {
                        "value": round(growth_rate, 1),
                        "unit": "%",
                        "period": f"{fiscal_year} vs {annual_reports[1]['fiscalDateEnding']}",
                        "source": "Alpha Vantage INCOME_STATEMENT (calculated)",
                        "notes": "Year-over-year revenue growth"
                    }
            
            # Calculate gross margin
            if all(key in most_recent and most_recent[key] != "None" for key in ["totalRevenue", "costOfRevenue"]):
                revenue = float(most_recent["totalRevenue"])
                cost_of_revenue = float(most_recent["costOfRevenue"])
                
                if revenue > 0:
                    gross_profit = revenue - cost_of_revenue
                    gross_margin = (gross_profit / revenue) * 100
                    metrics["gross_margin"] = {
                        "value": round(gross_margin, 1),
                        "unit": "%",
                        "period": fiscal_year,
                        "source": "Alpha Vantage INCOME_STATEMENT (calculated)",
                        "notes": "Gross margin percentage"
                    }
            
            # Extract R&D percentage if available
            if "researchAndDevelopment" in most_recent and most_recent["researchAndDevelopment"] != "None" and "totalRevenue" in most_recent:
                rd = float(most_recent["researchAndDevelopment"])
                revenue = float(most_recent["totalRevenue"])
                
                if revenue > 0:
                    rd_percentage = (rd / revenue) * 100
                    metrics["rd_percentage"] = {
                        "value": round(rd_percentage, 1),
                        "unit": "%",
                        "period": fiscal_year,
                        "source": "Alpha Vantage INCOME_STATEMENT (calculated)",
                        "notes": "R&D expenses as percentage of revenue"
                    }
        
        # 3. Get Cash Flow Statement (for operating cash flow)
        time.sleep(0.5)  # To avoid API rate limiting
        cashflow_params = {
            "function": "CASH_FLOW",
            "symbol": ticker,
            "apikey": ALPHA_VANTAGE_API_KEY
        }
        
        cashflow_response = requests.get(ALPHA_VANTAGE_BASE_URL, params=cashflow_params)
        cashflow_data = cashflow_response.json()
        
        if "annualReports" in cashflow_data and len(cashflow_data["annualReports"]) > 0:
            most_recent = cashflow_data["annualReports"][0]
            fiscal_year = most_recent.get("fiscalDateEnding", "")
            
            if "operatingCashflow" in most_recent and most_recent["operatingCashflow"] != "None":
                ocf = float(most_recent["operatingCashflow"]) / 1000000  # Convert to millions
                metrics["operating_cash_flow"] = {
                    "value": ocf,
                    "unit": "million USD",
                    "period": fiscal_year,
                    "source": "Alpha Vantage CASH_FLOW",
                    "notes": "Operating cash flow from cash flow statement"
                }
        
        # Save the metrics to cache
        save_to_cache(cache_key, "financials", metrics)
        
        return metrics
        
    except Exception as e:
        print(f"Error retrieving Alpha Vantage data for {ticker}: {e}")
        return None

def get_finnhub_financials(ticker: str) -> Dict:
    """
    Retrieve financial metrics from Finnhub API
    
    Args:
        ticker: Company ticker symbol
        
    Returns:
        Dictionary containing financial metrics
    """
    if not FINNHUB_API_KEY:
        return None
    
    print(f"Retrieving Finnhub data for {ticker}...")
    
    # Generate cache key
    cache_key = f"finnhub_{ticker}"
    
    # Check cache first
    cached_result = check_cache(cache_key, "financials")
    if cached_result:
        print(f"Using cached Finnhub data for {ticker}")
        return cached_result
    
    # Define the metrics to retrieve
    metrics = {}
    
    try:
        headers = {
            "X-Finnhub-Token": FINNHUB_API_KEY
        }
        
        # 1. Basic company profile
        profile_url = f"{FINNHUB_BASE_URL}/stock/profile2?symbol={ticker}"
        profile_response = requests.get(profile_url, headers=headers)
        profile_data = profile_response.json()
        
        if "name" in profile_data:
            # Extract employee count if available
            if "employeeTotal" in profile_data:
                metrics["employee_count"] = {
                    "value": profile_data["employeeTotal"],
                    "unit": "employees",
                    "period": "Latest",
                    "source": "Finnhub stock/profile2",
                    "notes": "Total employee count"
                }
            
            # Extract market cap if available
            if "marketCapitalization" in profile_data:
                market_cap = profile_data["marketCapitalization"]
                metrics["market_capitalization"] = {
                    "value": market_cap,
                    "unit": "million USD",
                    "period": "Latest",
                    "source": "Finnhub stock/profile2",
                    "notes": "Market capitalization in millions USD"
                }
        
        # 2. Financial metrics
        time.sleep(0.5)  # To avoid API rate limiting
        metrics_url = f"{FINNHUB_BASE_URL}/stock/metric?symbol={ticker}&metric=all"
        metrics_response = requests.get(metrics_url, headers=headers)
        metrics_data = metrics_response.json()
        
        if "metric" in metrics_data:
            metric_data = metrics_data["metric"]
            
            # Extract P/E ratio
            if "peBasicExclExtraTTM" in metric_data:
                metrics["price_to_earnings_ratio"] = {
                    "value": metric_data["peBasicExclExtraTTM"],
                    "unit": "ratio",
                    "period": "TTM",
                    "source": "Finnhub stock/metric",
                    "notes": "Price to earnings ratio (trailing twelve months)"
                }
            
            # Extract gross margin
            if "grossMarginTTM" in metric_data:
                metrics["gross_margin"] = {
                    "value": metric_data["grossMarginTTM"] * 100,  # Convert to percentage
                    "unit": "%",
                    "period": "TTM",
                    "source": "Finnhub stock/metric",
                    "notes": "Gross margin percentage (trailing twelve months)"
                }
            
            # Extract EBITDA margin
            if "ebitdaMarginTTM" in metric_data:
                metrics["ebitda_margin"] = {
                    "value": metric_data["ebitdaMarginTTM"] * 100,  # Convert to percentage
                    "unit": "%",
                    "period": "TTM",
                    "source": "Finnhub stock/metric",
                    "notes": "EBITDA margin percentage (trailing twelve months)"
                }
        
        # 3. Basic financials for revenue and cash flow
        time.sleep(0.5)  # To avoid API rate limiting
        financials_url = f"{FINNHUB_BASE_URL}/stock/financials-reported?symbol={ticker}&freq=annual"
        financials_response = requests.get(financials_url, headers=headers)
        financials_data = financials_response.json()
        
        if "data" in financials_data and len(financials_data["data"]) > 0:
            reports = financials_data["data"]
            
            # Sort by year (most recent first)
            reports.sort(key=lambda x: x.get("year", 0), reverse=True)
            
            if len(reports) > 0 and "report" in reports[0]:
                report = reports[0]["report"]
                year = reports[0].get("year", "")
                
                # Try to find revenue
                if "ic" in report and "revenue" in report["ic"]:
                    revenue = report["ic"]["revenue"] / 1000000  # Convert to millions
                    metrics["annual_revenue"] = {
                        "value": revenue,
                        "unit": "million USD",
                        "period": str(year),
                        "source": "Finnhub stock/financials-reported",
                        "notes": "Annual revenue from income statement"
                    }
                
                # Try to find operating cash flow
                if "cf" in report and "cashFlowFromOperatingActivities" in report["cf"]:
                    ocf = report["cf"]["cashFlowFromOperatingActivities"] / 1000000  # Convert to millions
                    metrics["operating_cash_flow"] = {
                        "value": ocf,
                        "unit": "million USD",
                        "period": str(year),
                        "source": "Finnhub stock/financials-reported",
                        "notes": "Operating cash flow from cash flow statement"
                    }
            
            # Calculate revenue growth if we have enough data
            if len(reports) > 1 and "report" in reports[1]:
                current_report = reports[0]["report"]
                previous_report = reports[1]["report"]
                
                if "ic" in current_report and "revenue" in current_report["ic"] and \
                   "ic" in previous_report and "revenue" in previous_report["ic"]:
                    current_revenue = current_report["ic"]["revenue"]
                    previous_revenue = previous_report["ic"]["revenue"]
                    
                    if previous_revenue > 0:
                        growth_rate = ((current_revenue - previous_revenue) / previous_revenue) * 100
                        metrics["revenue_growth"] = {
                            "value": round(growth_rate, 1),
                            "unit": "%",
                            "period": f"{reports[0].get('year', '')} vs {reports[1].get('year', '')}",
                            "source": "Finnhub stock/financials-reported (calculated)",
                            "notes": "Year-over-year revenue growth"
                        }
        
        # Save the metrics to cache
        save_to_cache(cache_key, "financials", metrics)
        
        return metrics
        
    except Exception as e:
        print(f"Error retrieving Finnhub data for {ticker}: {e}")
        return None

def get_competitor_financials_from_api(competitor: Dict[str, Any]) -> Dict[str, Any]:
    """
    Retrieve financial metrics for a competitor using financial APIs
    
    Args:
        competitor: Dictionary containing competitor information
        
    Returns:
        Dictionary containing financial metrics
    """
    ticker = competitor.get("ticker")
    name = competitor.get("name")
    
    print(f"Retrieving financial data for {name} ({ticker}) using APIs...")
    
    # Generate cache key for the combined API results
    cache_key = f"combined_api_{ticker}"
    
    # Check cache first
    cached_result = check_cache(cache_key, "financials")
    if cached_result:
        print(f"Using cached API data for {name}")
        return {
            "name": name,
            "ticker": ticker,
            "metrics": cached_result
        }
    
    # Start with Alpha Vantage (preferred for fundamental data)
    alpha_metrics = get_alpha_vantage_financials(ticker)
    
    # Then try Finnhub to fill gaps
    finnhub_metrics = get_finnhub_financials(ticker)
    
    # Combine metrics from both APIs, preferring Alpha Vantage when both have data
    combined_metrics = {}
    
    # Add Alpha Vantage metrics
    if alpha_metrics:
        combined_metrics.update(alpha_metrics)
    
    # Add Finnhub metrics where Alpha Vantage doesn't have data
    if finnhub_metrics:
        for key, value in finnhub_metrics.items():
            if key not in combined_metrics or combined_metrics[key].get("value") is None:
                combined_metrics[key] = value
    
    # Save combined metrics to cache
    save_to_cache(cache_key, "financials", combined_metrics)
    
    # If we got metrics from either API, return them
    if combined_metrics:
        print(f"Successfully retrieved API financial data for {name}")
        return {
            "name": name,
            "ticker": ticker,
            "metrics": combined_metrics
        }
    
    # If neither API worked, return None to trigger fallback to deep research
    print(f"No API financial data found for {name}, will use deep research fallback")
    return None

def get_competitor_financials(competitors: List[Dict[str, Any]], company_name: str, metrics: List[str]) -> List[Dict[str, Any]]:
    """
    Extract financial metrics for identified competitors.
    First tries to get data from financial APIs, falls back to Perplexity (Sonar-Pro or Deep) if needed.
    
    Args:
        competitors: List of competitor companies from find_competitors()
        company_name: Name of the input company (for caching)
        metrics: List of financial metrics to extract
        
    Returns:
        List of dictionaries containing financial metrics for each competitor
    """
    print(f"Retrieving financial data for {len(competitors)} competitors...")
    
    all_competitor_metrics = []
    competitors_for_perplexity = []

    essential_metrics = ["annual_revenue", "revenue_growth", "gross_margin", "ebitda_margin"]

    print("Step 1: Retrieving financial data from APIs (faster method)...")

    with ThreadPoolExecutor(max_workers=3) as executor:
        api_tasks = {
            executor.submit(get_competitor_financials_from_api, comp): comp
            for comp in competitors
        }

        for future in as_completed(api_tasks):
            comp = api_tasks[future]
            try:
                result = future.result()
                if result:
                    missing = [m for m in essential_metrics if m not in result["metrics"] or result["metrics"][m].get("value") is None]
                    if not missing:
                        all_competitor_metrics.append(result)
                    else:
                        print(f"Incomplete API data for {comp['name']} ({comp['ticker']}). Missing: {', '.join(missing)}")
                        comp["api_attempted"] = True
                        competitors_for_perplexity.append(comp)
                else:
                    comp["api_attempted"] = False
                    competitors_for_perplexity.append(comp)
            except Exception as e:
                print(f"Error processing API data for {comp['name']}: {e}")
                comp["api_attempted"] = False
                competitors_for_perplexity.append(comp)

    if competitors_for_perplexity:
        print(f"\nStep 2: Using Perplexity for {len(competitors_for_perplexity)} competitors with missing data...")

        for comp in competitors_for_perplexity:
            print(f"\nResearching: {comp['name']} ({comp['ticker']})")

            use_model = "sonar-deep-research" if not comp.get("api_attempted", True) else "sonar-pro"
            print(f"Using model: {use_model}")

            metrics_list = ", ".join(metrics)
            prompt = f"""
            Please extract the following financial metrics for {comp['name']} ({comp['ticker']}):
            - {metrics_list}

            Use reliable sources like 10-Ks, 10-Qs, or investor relations sites.
            Return the result in this JSON format:
            {{
              "company_metrics": [
                {{
                  "name": "{comp['name']}",
                  "ticker": "{comp['ticker']}",
                  "metrics": {{
                    "annual_revenue": {{"value": 123.4, "unit": "million USD", "period": "FY2023", "source": "URL"}},
                    ...
                  }}
                }}
              ]
            }}
            """

            headers = {
                "Authorization": f"Bearer {PERPLEXITY_API_KEY}",
                "Content-Type": "application/json",
            }

            data = {
                "model": use_model,
                "messages": [
                    {"role": "system", "content": "You are a financial analyst retrieving key metrics from public company reports."},
                    {"role": "user", "content": prompt}
                ],
                "max_tokens": 4096
            }

            try:
                response = requests.post(PERPLEXITY_API_URL, headers=headers, json=data)
                response.raise_for_status()
                content = response.json()["choices"][0]["message"]["content"]
                result = extract_json_from_response(content, "Generic")

                if "company_metrics" in result:
                    for dr_company in result["company_metrics"]:
                        existing_idx = next((i for i, c in enumerate(all_competitor_metrics)
                                             if c["ticker"] == dr_company["ticker"]), -1)
                        if existing_idx >= 0:
                            for k, v in dr_company["metrics"].items():
                                if k not in all_competitor_metrics[existing_idx]["metrics"] or \
                                   all_competitor_metrics[existing_idx]["metrics"][k].get("value") is None:
                                    all_competitor_metrics[existing_idx]["metrics"][k] = v
                        else:
                            all_competitor_metrics.append(dr_company)
            except Exception as e:
                print(f"Error retrieving Perplexity data for {comp['name']}: {e}")

    all_competitor_metrics = enrich_financial_data(all_competitor_metrics)

    print(f"\nSuccessfully retrieved financial data for {len(all_competitor_metrics)} of {len(competitors)} competitors")
    return all_competitor_metrics

def enrich_financial_data(competitor_metrics: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Fill in common data gaps with estimations and calculations
    """
    print("Enriching financial data with estimations for missing values...")
    
    for company in competitor_metrics:
        metrics = company.get("metrics", {})

        if not metrics:
            continue  # Skip if metrics is None
        
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
                    industry = company.get("industry", "Unknown").lower()
                    
                    # Different industries have different revenue per employee ratios
                    if "pharma" in industry or "healthcare" in industry or "biotech" in industry:
                        # Pharmaceutical industry average revenue per employee is higher
                        estimated_employees = int(revenue_usd / 500000)
                    elif "tech" in industry or "software" in industry:
                        # Tech companies often have higher revenue per employee
                        estimated_employees = int(revenue_usd / 450000)
                    elif "retail" in industry:
                        # Retail tends to be more labor-intensive
                        estimated_employees = int(revenue_usd / 250000)
                    elif "financial" in industry or "bank" in industry:
                        # Financial services are in the middle
                        estimated_employees = int(revenue_usd / 400000)
                    else:
                        # General estimate across industries
                        estimated_employees = int(revenue_usd / 350000)
                    
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


def save_results(company_name: str, company_industry: str, competitors: List[Dict[str, Any]], financials: List[Dict[str, Any]], output_dir: str):
    """
    Save competitor and financial data to JSON files.
    
    Args:
        company_name: Name of the original company
        company_industry: Industry of the original company
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
        "industry": company_industry,
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
    
    # Get file path from command line or environment variables
    file_path = args.file or os.environ.get("METRICS_FILE_PATH")
    
    # If not provided via arguments, look for files or ask for input
    if not file_path:
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
    else:
        print(f"Using provided file path: {file_path}")
    
    # Load input company financial metrics
    print(f"\nLoading company data from {file_path}...")
    company_data = load_company_metrics(file_path)
    
    if not company_data:
        print("Failed to load company data. Exiting.")
        return
    
    company_name = company_data.get('company_name', 'Unknown')
    # Allow industry override through command line
    industry = args.industry or company_data.get('industry', 'Unknown')
    
    # Create output directory - allow custom output dir through command line
    company_slug = company_name.lower().replace(' ', '_')
    base_output_dir = args.output_dir or "competitor_analysis"
    output_dir = os.path.join(base_output_dir, company_slug)
    os.makedirs(output_dir, exist_ok=True)
    
    print(f"\nStarting competitor analysis for {company_name}")
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
    num_competitors = args.competitors  # Get from command line arg with default of 6
    print(f"Looking for {num_competitors} most relevant competitors...")
    competitors = find_competitors(company_data, num_competitors=num_competitors)
    
    if not competitors:
        print("\nNo competitors found. Analysis cannot continue.")
        return
    
    print(f"\nFound {len(competitors)} competitors for {company_name}:")
    for i, comp in enumerate(competitors):
        print(f"  {i+1}. {comp['name']} ({comp['ticker']})")
    
    # Step 2: Get financial metrics for each competitor
    print(f"\n[STEP 2/3] Retrieving financial data for competitors...")
    financials = get_competitor_financials(competitors, company_name, metrics_to_extract)
    
    if not financials:
        print("\nFailed to retrieve financial data for any competitors.")
        # Save just the competitors without financials
        print("\n[STEP 3/3] Saving partial results...")
        save_results(company_name, industry, competitors, [], output_dir)
        return
    
    # Step 3: Save results
    print(f"\n[STEP 3/3] Saving analysis results...")
    save_results(company_name, industry, competitors, financials, output_dir)
    
    print("\nCompetitor analysis completed successfully!")
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