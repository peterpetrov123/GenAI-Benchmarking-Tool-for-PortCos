import os
import time
import json
import logging
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import requests
from bs4 import BeautifulSoup
import re
from io import StringIO
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv
import sys
from tqdm import tqdm
import random

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("market_data_scraper.log"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Constants
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(os.path.dirname(BASE_DIR), "financial_data", "market_data")
CACHE_DIR = os.path.join(DATA_DIR, "cache")
MAX_WORKERS = 8  # Increased for better parallelism but not too high to avoid rate limits
REQUEST_DELAY = 1.0  # Base delay between requests
MAX_RETRIES = 3
BACKOFF_FACTOR = 2

# API Keys (all free tier)
ALPHA_VANTAGE_API_KEY = "OOGYOPRCUSAPTP58"
FMP_API_KEY = ""  # Add your free Financial Modeling Prep API key if available
EOD_API_KEY = ""  # Add your free EOD Historical Data API key if available

# API call tracking
ALPHA_VANTAGE_API_CALLS = 0
ALPHA_VANTAGE_LAST_RESET = datetime.now()
FMP_API_CALLS = 0
FMP_LAST_RESET = datetime.now()

# Ensure directories exist
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(CACHE_DIR, exist_ok=True)

# User agent list to rotate and avoid rate limiting
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:89.0) Gecko/20100101 Firefox/89.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36"
]

# European countries and indices
EUROPEAN_COUNTRIES = [
    "united kingdom", "germany", "france", "italy", "spain", "netherlands", "switzerland", 
    "sweden", "belgium", "norway", "denmark", "finland", "austria", "ireland", "portugal", 
    "greece", "poland", "czech republic", "hungary"
]

EUROPEAN_INDICES = {
    "^STOXX50E": "EURO STOXX 50",
    "^FTSE": "FTSE 100",
    "^GDAXI": "DAX",
    "^FCHI": "CAC 40",
    "^IBEX": "IBEX 35",
    "^FTMIB": "FTSE MIB",
    "^AEX": "AEX",
    "^SMI": "Swiss Market Index"
}

def fetch_with_retry(url, headers=None, max_retries=MAX_RETRIES, delay=REQUEST_DELAY):
    """Fetch a URL with exponential backoff retry logic and rotating user agents"""
    if headers is None:
        headers = {
            "User-Agent": random.choice(USER_AGENTS)
        }
    
    retry_count = 0
    while retry_count <= max_retries:
        try:
            time.sleep(delay * (1 + random.random() * 0.5))  # Add jitter to delay
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            return response
        except requests.exceptions.RequestException as e:
            retry_count += 1
            if retry_count > max_retries:
                logger.error(f"Failed to fetch {url} after {max_retries} retries: {str(e)}")
                return None
            wait_time = delay * (BACKOFF_FACTOR ** retry_count) * (1 + random.random() * 0.5)
            logger.warning(f"Retrying {url} in {wait_time:.2f} seconds... (Attempt {retry_count}/{max_retries})")
            time.sleep(wait_time)
    
    return None

def get_alpha_vantage_data(endpoint, symbol, additional_params=None):
    """Generic function to get data from Alpha Vantage with rate limiting"""
    global ALPHA_VANTAGE_API_CALLS
    global ALPHA_VANTAGE_LAST_RESET
    
    # Create cache filename
    cache_file = os.path.join(CACHE_DIR, f"av_{endpoint}_{symbol.replace('^', '').replace('.', '_')}.json")
    
    # Check cache
    if os.path.exists(cache_file):
        file_age = datetime.now() - datetime.fromtimestamp(os.path.getmtime(cache_file))
        cache_duration = timedelta(days=30 if endpoint in ["INCOME_STATEMENT", "BALANCE_SHEET"] else 7)
        
        if file_age < cache_duration:
            try:
                with open(cache_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Error loading {endpoint} cache for {symbol}: {str(e)}")
    
    # Reset counter if we're in a new day
    now = datetime.now()
    if ALPHA_VANTAGE_LAST_RESET.date() != now.date():
        ALPHA_VANTAGE_API_CALLS = 0
        ALPHA_VANTAGE_LAST_RESET = now
    
    # Check if we're approaching the limit (500 calls/day for free tier)
    if ALPHA_VANTAGE_API_CALLS > 450:
        logger.warning("Approaching Alpha Vantage API limit. Using extended delay.")
        time.sleep(REQUEST_DELAY * 10)
    else:
        # Add jitter to delay to avoid rate limiting patterns
        time.sleep(REQUEST_DELAY * 2 * (1 + random.random()))
    
    # Increment API call counter
    ALPHA_VANTAGE_API_CALLS += 1
    
    # Build URL
    url = f"https://www.alphavantage.co/query?function={endpoint}&symbol={symbol}&apikey={ALPHA_VANTAGE_API_KEY}"
    if additional_params:
        for key, value in additional_params.items():
            url += f"&{key}={value}"
    
    logger.info(f"Fetching {endpoint} for {symbol} from Alpha Vantage (call #{ALPHA_VANTAGE_API_CALLS} today)")
    
    # Make request
    response = fetch_with_retry(url)
    if not response:
        logger.error(f"Failed to fetch {endpoint} for {symbol}")
        return {}
    
    try:
        data = response.json()
        
        # Check for errors or empty response
        if "Error Message" in data or not data or len(data) <= 1:
            if "Note" in data and "API call frequency" in data["Note"]:
                logger.warning("Alpha Vantage rate limit reached. Cooling down...")
                time.sleep(60)  # Wait a full minute
                ALPHA_VANTAGE_API_CALLS = 450  # Set counter high to trigger extended delays
            
            logger.warning(f"No valid {endpoint} data for {symbol}")
            return {}
        
        # Save to cache
        with open(cache_file, 'w') as f:
            json.dump(data, f, indent=4)
        
        return data
    
    except Exception as e:
        logger.error(f"Error parsing {endpoint} for {symbol}: {str(e)}")
        return {}

def scrape_yahoo_finance(symbol):
    """Scrape company data from Yahoo Finance"""
    cache_file = os.path.join(CACHE_DIR, f"yahoo_{symbol.replace('^', '').replace('.', '_')}.json")
    
    # Check cache
    if os.path.exists(cache_file):
        file_age = datetime.now() - datetime.fromtimestamp(os.path.getmtime(cache_file))
        if file_age < timedelta(days=7):
            try:
                with open(cache_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Error loading Yahoo Finance cache for {symbol}: {str(e)}")
    
    company_data = {
        'symbol': symbol,
        'data_source': 'Yahoo Finance'
    }
    
    # Make request to the profile page
    url = f"https://finance.yahoo.com/quote/{symbol}/profile"
    response = fetch_with_retry(url)
    if not response:
        logger.error(f"Failed to fetch Yahoo Finance profile for {symbol}")
        return company_data
    
    try:
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Extract company name
        name_element = soup.find('h1', class_='D(ib)')
        if name_element:
            company_data['name'] = name_element.text.strip()
        
        # Extract company description
        desc_element = soup.find('section', {'data-test': 'description'})
        if desc_element:
            company_data['description'] = desc_element.find('p').text.strip()
        
        # Extract sector and industry
        profile_elements = soup.find_all('p', class_='D(ib)')
        for element in profile_elements:
            text = element.text.strip()
            if 'Sector:' in text:
                company_data['sector'] = text.split('Sector:')[1].strip()
            elif 'Industry:' in text:
                company_data['industry'] = text.split('Industry:')[1].strip()
        
        # Extract country and employees
        address_elements = soup.find_all('p')
        for element in address_elements:
            text = element.text.strip()
            # Country is usually in the address
            if re.search(r'[A-Z]{2}[\s,]+\d{5}', text):  # Look for postal code pattern
                country_match = re.search(r'([A-Za-z]+)[\s,]+[A-Z]{2}[\s,]+\d{5}', text)
                if country_match:
                    company_data['country'] = "United States"  # US addresses
            elif any(country in text for country in ["United Kingdom", "Germany", "France"]):
                for country in ["United Kingdom", "Germany", "France", "Spain", "Italy"]:
                    if country in text:
                        company_data['country'] = country
                        break
            
            # Extract employee count
            employee_match = re.search(r'([0-9,]+)\s+employees', text)
            if employee_match:
                company_data['employees'] = int(employee_match.group(1).replace(',', ''))
        
        # Make another request to the key statistics page for financials
        stats_url = f"https://finance.yahoo.com/quote/{symbol}/key-statistics"
        stats_response = fetch_with_retry(stats_url)
        if stats_response:
            stats_soup = BeautifulSoup(stats_response.text, 'html.parser')
            
            # Extract market cap
            tables = stats_soup.find_all('table')
            for table in tables:
                rows = table.find_all('tr')
                for row in rows:
                    cells = row.find_all('td')
                    if len(cells) >= 2:
                        label = cells[0].text.strip()
                        value = cells[1].text.strip()
                        
                        if "Market Cap" in label:
                            company_data['market_cap'] = _parse_value(value)
                        elif "Revenue" in label:
                            company_data['revenue'] = _parse_value(value)
                        elif "Profit Margin" in label:
                            company_data['profit_margin'] = _parse_percentage(value)
                        elif "Operating Margin" in label:
                            company_data['operating_margin'] = _parse_percentage(value)
                        elif "Return on Assets" in label:
                            company_data['return_on_assets'] = _parse_percentage(value)
                        elif "Return on Equity" in label:
                            company_data['return_on_equity'] = _parse_percentage(value)
                        elif "Total Cash" in label:
                            company_data['cash'] = _parse_value(value)
                        elif "Total Debt" in label:
                            company_data['debt'] = _parse_value(value)
                        elif "Current Ratio" in label:
                            try:
                                company_data['current_ratio'] = float(value)
                            except ValueError:
                                pass
        
        # Save to cache
        with open(cache_file, 'w') as f:
            json.dump(company_data, f, indent=4)
        
        return company_data
    
    except Exception as e:
        logger.error(f"Error scraping Yahoo Finance for {symbol}: {str(e)}")
        return company_data

def scrape_marketscreener(symbol):
    """Scrape company data from MarketScreener"""
    cache_file = os.path.join(CACHE_DIR, f"ms_{symbol.replace('^', '').replace('.', '_')}.json")
    
    # Check cache
    if os.path.exists(cache_file):
        file_age = datetime.now() - datetime.fromtimestamp(os.path.getmtime(cache_file))
        if file_age < timedelta(days=7):
            try:
                with open(cache_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Error loading MarketScreener cache for {symbol}: {str(e)}")
    
    company_data = {
        'symbol': symbol,
        'data_source': 'MarketScreener'
    }
    
    # Map common exchange suffixes to marketscreener URL formats
    exchange_map = {
        '.L': '-GB',   # London
        '.PA': '-FR',  # Paris
        '.DE': '-DE',  # Germany
        '.MI': '-IT',  # Milan
        '.MC': '-ES',  # Madrid
        '.AS': '-NL',  # Amsterdam
        '.SW': '-CH'   # Switzerland
    }
    
    # Try to identify exchange suffix
    exchange_suffix = None
    for suffix, ms_suffix in exchange_map.items():
        if symbol.endswith(suffix):
            exchange_suffix = ms_suffix
            base_symbol = symbol.replace(suffix, '')
            break
    
    if not exchange_suffix:
        # Default to US if no recognized suffix
        exchange_suffix = '-US'
        base_symbol = symbol
    
    url = f"https://www.marketscreener.com/quote/{base_symbol}{exchange_suffix}/"
    response = fetch_with_retry(url)
    if not response:
        logger.error(f"Failed to fetch MarketScreener data for {symbol}")
        return company_data
    
    try:
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Extract company name
        name_element = soup.select_one('h1.instrumentTitle')
        if name_element:
            company_data['name'] = name_element.text.strip()
        
        # Extract sector and industry
        sector_elements = soup.select('.instrumentinfosleft tr')
        for element in sector_elements:
            cells = element.select('td')
            if len(cells) >= 2:
                label = cells[0].text.strip()
                value = cells[1].text.strip()
                
                if "Sector" in label:
                    company_data['sector'] = value
                elif "Industry" in label:
                    company_data['industry'] = value
                elif "Country" in label:
                    company_data['country'] = value
        
        # Extract financial metrics
        finance_elements = soup.select('.financeTable tr')
        for element in finance_elements:
            cells = element.select('td')
            if len(cells) >= 2:
                label = cells[0].text.strip()
                value = cells[1].text.strip()
                
                if "Market Cap" in label:
                    company_data['market_cap'] = _parse_value(value)
                elif "Revenue" in label:
                    company_data['revenue'] = _parse_value(value)
                elif "Net income" in label:
                    company_data['net_income'] = _parse_value(value)
                elif "P/E ratio" in label:
                    try:
                        company_data['pe_ratio'] = float(value.replace(',', '.'))
                    except ValueError:
                        pass
        
        # Save to cache
        with open(cache_file, 'w') as f:
            json.dump(company_data, f, indent=4)
        
        return company_data
    
    except Exception as e:
        logger.error(f"Error scraping MarketScreener for {symbol}: {str(e)}")
        return company_data

def get_company_info(symbol, name=None, country=None, source=None):
    """Get comprehensive company information by combining multiple data sources"""
    logger.info(f"Getting comprehensive info for {symbol}")
    
    # Default info with basic fields
    company_info = {
        'symbol': symbol,
        'name': name or symbol,
        'industry': 'Unknown',
        'sector': 'Unknown',
        'country': country or 'Unknown',
        'region': _map_country_to_region(country) if country else 'Unknown',
        'revenue': None,
        'employees': None,
        'market_cap': None,
        'currency': 'Unknown',
        'exchange': 'Unknown',
        'website': '',
        'data_source': source or 'Unknown',
        'last_updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    
    # Try Alpha Vantage first
    av_overview = get_alpha_vantage_data("OVERVIEW", symbol)
    if av_overview and len(av_overview) > 1:
        company_info.update({
            'name': av_overview.get('Name', company_info['name']),
            'industry': av_overview.get('Industry', company_info['industry']),
            'sector': av_overview.get('Sector', company_info['sector']),
            'country': av_overview.get('Country', company_info['country']),
            'region': _map_country_to_region(av_overview.get('Country', None)) or company_info['region'],
            'employees': _parse_value(av_overview.get('FullTimeEmployees')),
            'market_cap': _parse_value(av_overview.get('MarketCapitalization')),
            'currency': av_overview.get('Currency', company_info['currency']),
            'exchange': av_overview.get('Exchange', company_info['exchange']),
            'website': av_overview.get('Address', ''),
            'data_source': 'Alpha Vantage'
        })
    
    # Try Yahoo Finance scraping if we don't have enough data
    if company_info['industry'] == 'Unknown' or company_info['sector'] == 'Unknown':
        yahoo_data = scrape_yahoo_finance(symbol)
        if yahoo_data:
            # Update info from Yahoo Finance
            for field in ['name', 'industry', 'sector', 'country', 'employees', 'market_cap', 'revenue']:
                if field in yahoo_data and yahoo_data[field] and (company_info[field] is None or company_info[field] == 'Unknown'):
                    company_info[field] = yahoo_data[field]
            
            # Update region if country was updated
            if yahoo_data.get('country') and company_info['country'] != 'Unknown':
                company_info['region'] = _map_country_to_region(company_info['country'])
            
            if company_info['data_source'] == 'Unknown':
                company_info['data_source'] = 'Yahoo Finance'
            else:
                company_info['data_source'] += ', Yahoo Finance'
    
    # Try MarketScreener as a third source
    if company_info['industry'] == 'Unknown' or company_info['sector'] == 'Unknown':
        ms_data = scrape_marketscreener(symbol)
        if ms_data:
            for field in ['name', 'industry', 'sector', 'country', 'market_cap', 'revenue']:
                if field in ms_data and ms_data[field] and (company_info[field] is None or company_info[field] == 'Unknown'):
                    company_info[field] = ms_data[field]
            
            # Update region if country was updated
            if ms_data.get('country') and company_info['country'] != 'Unknown':
                company_info['region'] = _map_country_to_region(company_info['country'])
            
            if company_info['data_source'] == 'Unknown':
                company_info['data_source'] = 'MarketScreener'
            else:
                company_info['data_source'] += ', MarketScreener'
    
    # Attempt to make educated guesses for missing data
    if company_info['industry'] == 'Unknown' and company_info['name'] != symbol:
        inferred_industry = _infer_industry(company_info['name'])
        if inferred_industry != "Other":
            company_info['industry'] = inferred_industry
            if company_info['data_source'] != 'Unknown':
                company_info['data_source'] += ', Inferred'
            else:
                company_info['data_source'] = 'Inferred'
    
    return company_info

def _parse_value(value):
    """Parse numeric values from various formats"""
    if value is None:
        return None
    
    if isinstance(value, (int, float)):
        return value
    
    if isinstance(value, str):
        # Remove currency symbols, commas, etc.
        cleaned = value.replace(',', '').replace('$', '').replace('€', '').replace('£', '')
        
        # Handle "B" for billion, "M" for million, etc.
        if 'B' in cleaned or 'b' in cleaned:
            cleaned = re.sub(r'[Bb]', '', cleaned)
            try:
                return float(cleaned) * 1_000_000_000
            except ValueError:
                pass
        elif 'M' in cleaned or 'm' in cleaned:
            cleaned = re.sub(r'[Mm]', '', cleaned)
            try:
                return float(cleaned) * 1_000_000
            except ValueError:
                pass
        elif 'K' in cleaned or 'k' in cleaned:
            cleaned = re.sub(r'[Kk]', '', cleaned)
            try:
                return float(cleaned) * 1_000
            except ValueError:
                pass
        
        # Try direct conversion
        try:
            return float(cleaned)
        except ValueError:
            pass
    
    return None

def _parse_percentage(value):
    """Parse percentage values"""
    if value is None:
        return None
    
    if isinstance(value, str):
        # Remove % sign and convert to float
        cleaned = value.replace('%', '').replace(',', '.')
        try:
            return float(cleaned)
        except ValueError:
            pass
    
    return None

def _map_country_to_region(country):
    """Map country to geographic region"""
    if not country or country == 'Unknown':
        return "Unknown"
        
    europe = ['United Kingdom', 'Germany', 'France', 'Italy', 'Spain', 'Netherlands', 
              'Switzerland', 'Sweden', 'Belgium', 'Denmark', 'Finland', 'Norway', 
              'Austria', 'Ireland', 'Portugal', 'Greece', 'Luxembourg', 'Poland',
              'Czech Republic', 'Hungary', 'Slovakia', 'Slovenia', 'Croatia', 
              'Estonia', 'Latvia', 'Lithuania', 'Romania', 'Bulgaria', 'Cyprus', 'Malta']
    
    north_america = ['United States', 'Canada', 'Mexico', 'USA']
    
    asia_pacific = ['Japan', 'China', 'South Korea', 'Taiwan', 'India', 'Australia', 
                    'Hong Kong', 'Singapore', 'Malaysia', 'Thailand', 'Indonesia', 
                    'Philippines', 'Vietnam', 'New Zealand']
    
    # Normalize input
    country_norm = country.strip().title()
    
    if any(country_norm in eu_country.title() for eu_country in europe):
        return 'Europe'
    elif any(country_norm in na_country.title() for na_country in north_america):
        return 'North America'
    elif any(country_norm in ap_country.title() for ap_country in asia_pacific):
        return 'Asia Pacific'
    else:
        return 'Other'

def _infer_industry(company_name):
    """Infer company industry from its name"""
    if not company_name:
        return "Unknown"
        
    # Common industry keywords
    industry_keywords = {
        "Healthcare": ["health", "medical", "hospital", "clinic", "care", "pharma", "therapeutic"],
        "Technology": ["tech", "software", "digital", "cyber", "systems", "IT", "information", "data"],
        "Financial Services": ["bank", "finance", "invest", "capital", "financial", "asset", "insurance", "credit"],
        "Energy": ["energy", "oil", "gas", "solar", "power", "renewable", "petroleum"],
        "Manufacturing": ["manufacturing", "industrial", "factory", "product", "fabrication", "steel", "metal"],
        "Retail": ["retail", "store", "shop", "mart", "market", "consumer", "goods"],
        "Telecommunications": ["telecom", "communication", "network", "mobile", "wireless", "broadband"],
        "Real Estate": ["property", "real estate", "realty", "construction", "building", "homes"],
        "Transportation": ["transport", "logistics", "shipping", "delivery", "freight", "airline", "railway"],
        "Media": ["media", "entertainment", "film", "game", "broadcast", "production", "publisher"]
    }
    
    # Score each industry based on keyword matches
    scores = {industry: 0 for industry in industry_keywords}
    
    for industry, keywords in industry_keywords.items():
        for keyword in keywords:
            if keyword.lower() in company_name.lower():
                scores[industry] += 1
    
    # Return the industry with the highest score, or "Other" if no matches
    max_score = max(scores.values())
    if max_score > 0:
        return max(scores.items(), key=lambda x: x[1])[0]
    else:
        return "Other"

def create_fallback_companies():
    """Create a comprehensive list of important European companies"""
    # This contains the most important companies for each major European index
    # Much more extensive than before
    companies = []
    
    # FTSE 100 (UK)
    ftse_companies = [
        {'symbol': 'HSBA.L', 'name': 'HSBC Holdings', 'sector': 'Financial Services', 'country': 'United Kingdom'},
        {'symbol': 'AZN.L', 'name': 'AstraZeneca', 'sector': 'Healthcare', 'country': 'United Kingdom'},
        {'symbol': 'SHEL.L', 'name': 'Shell', 'sector': 'Energy', 'country': 'United Kingdom'},
        {'symbol': 'ULVR.L', 'name': 'Unilever', 'sector': 'Consumer Goods', 'country': 'United Kingdom'},
        {'symbol': 'RIO.L', 'name': 'Rio Tinto', 'sector': 'Basic Materials', 'country': 'United Kingdom'},
        {'symbol': 'BP.L', 'name': 'BP', 'sector': 'Energy', 'country': 'United Kingdom'},
        {'symbol': 'GSK.L', 'name': 'GSK', 'sector': 'Healthcare', 'country': 'United Kingdom'},
        {'symbol': 'DGE.L', 'name': 'Diageo', 'sector': 'Consumer Goods', 'country': 'United Kingdom'},
        {'symbol': 'LLOY.L', 'name': 'Lloyds Banking Group', 'sector': 'Financial Services', 'country': 'United Kingdom'},
        {'symbol': 'VOD.L', 'name': 'Vodafone Group', 'sector': 'Telecommunications', 'country': 'United Kingdom'},
        {'symbol': 'BARC.L', 'name': 'Barclays', 'sector': 'Financial Services', 'country': 'United Kingdom'},
        {'symbol': 'BATS.L', 'name': 'British American Tobacco', 'sector': 'Consumer Goods', 'country': 'United Kingdom'},
        {'symbol': 'REL.L', 'name': 'RELX', 'sector': 'Media', 'country': 'United Kingdom'},
        {'symbol': 'NWG.L', 'name': 'NatWest Group', 'sector': 'Financial Services', 'country': 'United Kingdom'},
        {'symbol': 'PRU.L', 'name': 'Prudential', 'sector': 'Financial Services', 'country': 'United Kingdom'},
    ]
    companies.extend(ftse_companies)
    
    # DAX (Germany)
    dax_companies = [
        {'symbol': 'SAP.DE', 'name': 'SAP', 'sector': 'Technology', 'country': 'Germany'},
        {'symbol': 'SIE.DE', 'name': 'Siemens', 'sector': 'Industrials', 'country': 'Germany'},
        {'symbol': 'ALV.DE', 'name': 'Allianz', 'sector': 'Financial Services', 'country': 'Germany'},
        {'symbol': 'DTE.DE', 'name': 'Deutsche Telekom', 'sector': 'Telecommunications', 'country': 'Germany'},
        {'symbol': 'BAYN.DE', 'name': 'Bayer', 'sector': 'Healthcare', 'country': 'Germany'},
        {'symbol': 'BMW.DE', 'name': 'BMW', 'sector': 'Consumer Cyclical', 'country': 'Germany'},
        {'symbol': 'BAS.DE', 'name': 'BASF', 'sector': 'Basic Materials', 'country': 'Germany'},
        {'symbol': 'DB1.DE', 'name': 'Deutsche Börse', 'sector': 'Financial Services', 'country': 'Germany'},
        {'symbol': 'MUV2.DE', 'name': 'Munich Re', 'sector': 'Financial Services', 'country': 'Germany'},
        {'symbol': 'ADS.DE', 'name': 'Adidas', 'sector': 'Consumer Cyclical', 'country': 'Germany'},
        {'symbol': 'VOW3.DE', 'name': 'Volkswagen', 'sector': 'Consumer Cyclical', 'country': 'Germany'},
        {'symbol': 'HEN3.DE', 'name': 'Henkel', 'sector': 'Consumer Defensive', 'country': 'Germany'},
        {'symbol': 'DBK.DE', 'name': 'Deutsche Bank', 'sector': 'Financial Services', 'country': 'Germany'},
        {'symbol': 'RWE.DE', 'name': 'RWE', 'sector': 'Utilities', 'country': 'Germany'},
        {'symbol': 'HEI.DE', 'name': 'HeidelbergCement', 'sector': 'Basic Materials', 'country': 'Germany'},
    ]
    companies.extend(dax_companies)
    
    # CAC 40 (France)
    cac_companies = [
        {'symbol': 'MC.PA', 'name': 'LVMH', 'sector': 'Consumer Cyclical', 'country': 'France'},
        {'symbol': 'OR.PA', 'name': 'L\'Oréal', 'sector': 'Consumer Defensive', 'country': 'France'},
        {'symbol': 'SAN.PA', 'name': 'Sanofi', 'sector': 'Healthcare', 'country': 'France'},
        {'symbol': 'AIR.PA', 'name': 'Airbus', 'sector': 'Industrials', 'country': 'France'},
        {'symbol': 'BNP.PA', 'name': 'BNP Paribas', 'sector': 'Financial Services', 'country': 'France'},
        {'symbol': 'CS.PA', 'name': 'AXA', 'sector': 'Financial Services', 'country': 'France'},
        {'symbol': 'KER.PA', 'name': 'Kering', 'sector': 'Consumer Cyclical', 'country': 'France'},
        {'symbol': 'RI.PA', 'name': 'Pernod Ricard', 'sector': 'Consumer Defensive', 'country': 'France'},
        {'symbol': 'FP.PA', 'name': 'TotalEnergies', 'sector': 'Energy', 'country': 'France'},
        {'symbol': 'CA.PA', 'name': 'Carrefour', 'sector': 'Consumer Defensive', 'country': 'France'},
        {'symbol': 'BN.PA', 'name': 'Danone', 'sector': 'Consumer Defensive', 'country': 'France'},
        {'symbol': 'SGO.PA', 'name': 'Saint-Gobain', 'sector': 'Industrials', 'country': 'France'},
        {'symbol': 'ACA.PA', 'name': 'Crédit Agricole', 'sector': 'Financial Services', 'country': 'France'},
        {'symbol': 'GLE.PA', 'name': 'Société Générale', 'sector': 'Financial Services', 'country': 'France'},
        {'symbol': 'RMS.PA', 'name': 'Hermès International', 'sector': 'Consumer Cyclical', 'country': 'France'},
    ]
    companies.extend(cac_companies)
    
    # Other Major European
    other_major = [
        # Switzerland
        {'symbol': 'NESN.SW', 'name': 'Nestlé', 'sector': 'Consumer Defensive', 'country': 'Switzerland'},
        {'symbol': 'ROG.SW', 'name': 'Roche', 'sector': 'Healthcare', 'country': 'Switzerland'},
        {'symbol': 'NOVN.SW', 'name': 'Novartis', 'sector': 'Healthcare', 'country': 'Switzerland'},
        {'symbol': 'UBSG.SW', 'name': 'UBS Group', 'sector': 'Financial Services', 'country': 'Switzerland'},
        {'symbol': 'CFR.SW', 'name': 'Richemont', 'sector': 'Consumer Cyclical', 'country': 'Switzerland'},
        
        # Netherlands
        {'symbol': 'ASML.AS', 'name': 'ASML Holding', 'sector': 'Technology', 'country': 'Netherlands'},
        {'symbol': 'AD.AS', 'name': 'Ahold Delhaize', 'sector': 'Consumer Defensive', 'country': 'Netherlands'},
        {'symbol': 'INGA.AS', 'name': 'ING Groep', 'sector': 'Financial Services', 'country': 'Netherlands'},
        {'symbol': 'PHIA.AS', 'name': 'Philips', 'sector': 'Healthcare', 'country': 'Netherlands'},
        {'symbol': 'UNA.AS', 'name': 'Unilever', 'sector': 'Consumer Defensive', 'country': 'Netherlands'},
        
        # Spain
        {'symbol': 'SAN.MC', 'name': 'Banco Santander', 'sector': 'Financial Services', 'country': 'Spain'},
        {'symbol': 'BBVA.MC', 'name': 'BBVA', 'sector': 'Financial Services', 'country': 'Spain'},
        {'symbol': 'ITX.MC', 'name': 'Inditex', 'sector': 'Consumer Cyclical', 'country': 'Spain'},
        {'symbol': 'IBE.MC', 'name': 'Iberdrola', 'sector': 'Utilities', 'country': 'Spain'},
        {'symbol': 'TEF.MC', 'name': 'Telefónica', 'sector': 'Telecommunications', 'country': 'Spain'},
        
        # Italy
        {'symbol': 'ENI.MI', 'name': 'Eni', 'sector': 'Energy', 'country': 'Italy'},
        {'symbol': 'ENEL.MI', 'name': 'Enel', 'sector': 'Utilities', 'country': 'Italy'},
        {'symbol': 'ISP.MI', 'name': 'Intesa Sanpaolo', 'sector': 'Financial Services', 'country': 'Italy'},
        {'symbol': 'UCG.MI', 'name': 'UniCredit', 'sector': 'Financial Services', 'country': 'Italy'},
        
        # Sweden
        {'symbol': 'ERIC-B.ST', 'name': 'Ericsson', 'sector': 'Technology', 'country': 'Sweden'},
        {'symbol': 'VOLV-B.ST', 'name': 'Volvo', 'sector': 'Industrials', 'country': 'Sweden'},
        
        # Denmark
        {'symbol': 'NOVO-B.CO', 'name': 'Novo Nordisk', 'sector': 'Healthcare', 'country': 'Denmark'},
        {'symbol': 'MAERSK-B.CO', 'name': 'Maersk', 'sector': 'Industrials', 'country': 'Denmark'},
    ]
    companies.extend(other_major)
    
    # Manually add more European companies as needed
    additional_companies = [
        # Technology
        {'symbol': 'STM.PA', 'name': 'STMicroelectronics', 'sector': 'Technology', 'country': 'France'},
        {'symbol': 'CAP.PA', 'name': 'Capgemini', 'sector': 'Technology', 'country': 'France'},
        {'symbol': 'WDI.DE', 'name': 'Wirecard', 'sector': 'Technology', 'country': 'Germany'},
        {'symbol': 'SAF.PA', 'name': 'Safran', 'sector': 'Industrials', 'country': 'France'},
        
        # Healthcare
        {'symbol': 'SHL.DE', 'name': 'Siemens Healthineers', 'sector': 'Healthcare', 'country': 'Germany'},
        {'symbol': 'GIVN.SW', 'name': 'Givaudan', 'sector': 'Basic Materials', 'country': 'Switzerland'},
        {'symbol': 'FRE.DE', 'name': 'Fresenius', 'sector': 'Healthcare', 'country': 'Germany'},
        {'symbol': 'FME.DE', 'name': 'Fresenius Medical Care', 'sector': 'Healthcare', 'country': 'Germany'},
        
        # Industrials
        {'symbol': 'SU.PA', 'name': 'Schneider Electric', 'sector': 'Industrials', 'country': 'France'},
        {'symbol': 'UHR.SW', 'name': 'Swatch Group', 'sector': 'Consumer Cyclical', 'country': 'Switzerland'},
        {'symbol': 'LR.PA', 'name': 'Legrand', 'sector': 'Industrials', 'country': 'France'},
        
        # Consumer
        {'symbol': 'ABI.BR', 'name': 'Anheuser-Busch InBev', 'sector': 'Consumer Defensive', 'country': 'Belgium'},
        {'symbol': 'HEIA.AS', 'name': 'Heineken', 'sector': 'Consumer Defensive', 'country': 'Netherlands'},
        {'symbol': 'PRX.AS', 'name': 'Prosus', 'sector': 'Technology', 'country': 'Netherlands'},
        
        # Financial Services
        {'symbol': 'ZURN.SW', 'name': 'Zurich Insurance', 'sector': 'Financial Services', 'country': 'Switzerland'},
        {'symbol': 'CSGN.SW', 'name': 'Credit Suisse', 'sector': 'Financial Services', 'country': 'Switzerland'},
        {'symbol': 'KBC.BR', 'name': 'KBC Group', 'sector': 'Financial Services', 'country': 'Belgium'},
        
        # Smaller Cap Companies (for better SME coverage)
        {'symbol': 'EVO.ST', 'name': 'Evolution Gaming', 'sector': 'Consumer Cyclical', 'country': 'Sweden'},
        {'symbol': 'CLA.DE', 'name': 'ClariantAG', 'sector': 'Basic Materials', 'country': 'Germany'},
        {'symbol': 'AGN.AS', 'name': 'Aegon', 'sector': 'Financial Services', 'country': 'Netherlands'},
        {'symbol': 'SW.PA', 'name': 'Sodexo', 'sector': 'Consumer Cyclical', 'country': 'France'},
        {'symbol': 'GFC.PA', 'name': 'Gecina', 'sector': 'Real Estate', 'country': 'France'},
        {'symbol': 'DOM.DE', 'name': 'Dominion Energy', 'sector': 'Utilities', 'country': 'Germany'},
    ]
    companies.extend(additional_companies)
    
    # Add region information
    for company in companies:
        company['region'] = _map_country_to_region(company.get('country'))
    
    logger.info(f"Created fallback list with {len(companies)} major European companies")
    return companies

def compile_european_companies():
    """Compile a list of European companies from multiple sources"""
    all_companies = []
    unique_symbols = set()
    
    # Start with our manually curated list of important companies
    logger.info("Adding manually curated European companies")
    fallback_companies = create_fallback_companies()
    
    for company in fallback_companies:
        symbol = company.get('symbol')
        if symbol not in unique_symbols:
            company['source'] = 'Curated List'
            all_companies.append(company)
            unique_symbols.add(symbol)
    
    # Try to get companies from Alpha Vantage listings
    logger.info("Getting companies from Alpha Vantage")
    av_listings = get_alpha_vantage_data("LISTING_STATUS", "")
    
    if av_listings and av_listings.get('symbolsList'):
        european_exchanges = [
            'LSE', 'XETRA', 'PAR', 'AMS', 'BIT', 'SW', 'SIX', 'CPH',
            'STO', 'OSL', 'HEL', 'IBEX', 'VIE', 'BRU', 'LIS', 'ATH'
        ]
        
        for listing in av_listings.get('symbolsList', []):
            symbol = listing.get('symbol')
            name = listing.get('name')
            exchange = listing.get('exchange')
            
            # Skip if already processed
            if symbol in unique_symbols:
                continue
            
            # Only add if it's from a European exchange
            if exchange in european_exchanges:
                all_companies.append({
                    'symbol': symbol,
                    'name': name,
                    'exchange': exchange,
                    'source': 'Alpha Vantage'
                })
                unique_symbols.add(symbol)
    
    # Use web scraping to find additional European companies
    for country in ['uk', 'germany', 'france', 'italy', 'spain']:
        try:
            logger.info(f"Scraping top companies from {country}")
            companies = _scrape_top_companies(country)
            
            for company in companies:
                symbol = company.get('symbol')
                if symbol and symbol not in unique_symbols:
                    all_companies.append(company)
                    unique_symbols.add(symbol)
        except Exception as e:
            logger.error(f"Error scraping top companies for {country}: {str(e)}")
    
    logger.info(f"Compiled {len(all_companies)} unique European companies")
    return all_companies

def _scrape_top_companies(country):
    """Scrape top companies from a specific country"""
    # Map country to URL
    url_map = {
        'uk': 'https://companiesmarketcap.com/united-kingdom/largest-companies-in-the-uk-by-market-cap/',
        'germany': 'https://companiesmarketcap.com/germany/largest-companies-in-germany-by-market-cap/',
        'france': 'https://companiesmarketcap.com/france/largest-companies-in-france-by-market-cap/',
        'italy': 'https://companiesmarketcap.com/italy/largest-companies-in-italy-by-market-cap/',
        'spain': 'https://companiesmarketcap.com/spain/largest-companies-in-spain-by-market-cap/'
    }
    
    # Map country to ISO code
    country_map = {
        'uk': 'United Kingdom',
        'germany': 'Germany',
        'france': 'France',
        'italy': 'Italy',
        'spain': 'Spain'
    }
    
    # Map country to common ticker suffixes
    suffix_map = {
        'uk': '.L',
        'germany': '.DE',
        'france': '.PA',
        'italy': '.MI',
        'spain': '.MC'
    }
    
    if country not in url_map:
        return []
    
    url = url_map[country]
    response = fetch_with_retry(url)
    if not response:
        logger.error(f"Failed to fetch top companies for {country}")
        return []
    
    companies = []
    
    try:
        soup = BeautifulSoup(response.text, 'html.parser')
        rows = soup.select('.company-ranking')
        
        for row in rows:
            name_element = row.select_one('.company-name')
            if not name_element:
                continue
                
            name = name_element.text.strip()
            
            # Try to find the ticker symbol
            ticker_element = row.select_one('.company-code')
            ticker = ticker_element.text.strip() if ticker_element else ""
            
            # Add country's suffix if not there
            if ticker and suffix_map[country] not in ticker:
                ticker += suffix_map[country]
            
            # Find market cap
            market_cap_element = row.select_one('.tdv-right')
            market_cap_str = market_cap_element.text.strip() if market_cap_element else ""
            market_cap = _parse_value(market_cap_str)
            
            companies.append({
                'symbol': ticker,
                'name': name,
                'country': country_map[country],
                'region': 'Europe',
                'market_cap': market_cap,
                'source': 'Web Scraping'
            })
    
    except Exception as e:
        logger.error(f"Error parsing top companies for {country}: {str(e)}")
    
    return companies

def gather_company_details(companies, max_companies=None):
    """Gather detailed information for a list of companies"""
    # Limit the number of companies to process if specified
    if max_companies and len(companies) > max_companies:
        logger.info(f"Limiting to {max_companies} companies")
        
        # Prioritize companies with more information
        def company_score(company):
            score = 0
            # Companies with market cap data are more important
            if company.get('market_cap'):
                score += 100
            # Companies with sector information are more complete
            if company.get('sector') and company['sector'] != 'Unknown':
                score += 50
            # Companies with country information are more complete
            if company.get('country') and company['country'] != 'Unknown':
                score += 25
            # Prioritize European companies
            if company.get('region') == 'Europe':
                score += 10
            # Prefer manually curated companies
            if company.get('source') == 'Curated List':
                score += 200
            return score
        
        companies = sorted(companies, key=company_score, reverse=True)
        companies = companies[:max_companies]
    
    logger.info(f"Gathering detailed information for {len(companies)} companies")
    
    detailed_companies = []
    
    # Use ThreadPoolExecutor for parallel processing
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # Prepare tasks
        future_to_company = {}
        for company in companies:
            symbol = company.get('symbol')
            name = company.get('name')
            country = company.get('country')
            source = company.get('source')
            
            future = executor.submit(get_company_info, symbol, name, country, source)
            future_to_company[future] = company
        
        # Process results as they complete
        for future in tqdm(as_completed(future_to_company), total=len(future_to_company), desc="Processing companies"):
            company = future_to_company[future]
            symbol = company.get('symbol')
            
            try:
                detailed_info = future.result()
                if detailed_info:
                    # If the company already had some good data, preserve it
                    for key, value in company.items():
                        if (value and value != 'Unknown' and value != '' and 
                            (detailed_info.get(key) is None or detailed_info.get(key) == 'Unknown')):
                            detailed_info[key] = value
                    
                    detailed_companies.append(detailed_info)
                else:
                    logger.warning(f"No detailed info for {symbol}")
            except Exception as e:
                logger.error(f"Error processing {symbol}: {str(e)}")
    
    logger.info(f"Successfully gathered detailed data for {len(detailed_companies)} companies")
    return detailed_companies

def fetch_financial_data(symbol):
    """Fetch financial data from Alpha Vantage and other sources"""
    # Get income statement and balance sheet from Alpha Vantage
    income_data = get_alpha_vantage_data("INCOME_STATEMENT", symbol)
    balance_data = get_alpha_vantage_data("BALANCE_SHEET", symbol)
    
    # Try to get data from Yahoo Finance if Alpha Vantage doesn't provide enough
    yahoo_data = scrape_yahoo_finance(symbol)
    
    # Combine into a single dataset
    metrics = {
        'symbol': symbol,
        'name': None,
        'sector': None,
        'industry': None,
        'country': None,
        'revenue': None,
        'net_income': None,
        'gross_profit': None,
        'operating_income': None,
        'ebitda': None,
        'total_assets': None,
        'total_liabilities': None,
        'total_equity': None,
        'current_assets': None,
        'current_liabilities': None,
        'cash': None,
        'pe_ratio': None,
        'market_cap': None,
        'employees': None,
        'profit_margin': None,
        'operating_margin': None,
        'data_source': None,
        'last_updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    
    # Extract from Alpha Vantage income statement
    if income_data and 'annualReports' in income_data and len(income_data['annualReports']) > 0:
        most_recent = income_data['annualReports'][0]
        metrics['fiscal_year_end'] = most_recent.get('fiscalDateEnding', 'Unknown')
        metrics['revenue'] = _parse_value(most_recent.get('totalRevenue'))
        metrics['gross_profit'] = _parse_value(most_recent.get('grossProfit'))
        metrics['operating_income'] = _parse_value(most_recent.get('operatingIncome'))
        metrics['net_income'] = _parse_value(most_recent.get('netIncome'))
        metrics['ebitda'] = _parse_value(most_recent.get('ebitda'))
        
        if not metrics['data_source']:
            metrics['data_source'] = 'Alpha Vantage Income Statement'
        else:
            metrics['data_source'] += ', Alpha Vantage Income Statement'
    
    # Extract from Alpha Vantage balance sheet
    if balance_data and 'annualReports' in balance_data and len(balance_data['annualReports']) > 0:
        most_recent = balance_data['annualReports'][0]
        metrics['total_assets'] = _parse_value(most_recent.get('totalAssets'))
        metrics['total_liabilities'] = _parse_value(most_recent.get('totalLiabilities'))
        metrics['total_equity'] = _parse_value(most_recent.get('totalShareholderEquity'))
        metrics['current_assets'] = _parse_value(most_recent.get('totalCurrentAssets'))
        metrics['current_liabilities'] = _parse_value(most_recent.get('totalCurrentLiabilities'))
        metrics['cash'] = _parse_value(most_recent.get('cashAndCashEquivalentsAtCarryingValue'))
        
        if not metrics['data_source']:
            metrics['data_source'] = 'Alpha Vantage Balance Sheet'
        else:
            metrics['data_source'] += ', Alpha Vantage Balance Sheet'
    
    # Add Yahoo Finance data
    if yahoo_data:
        # Basic company info
        metrics['name'] = yahoo_data.get('name', metrics['name'])
        metrics['sector'] = yahoo_data.get('sector', metrics['sector'])
        metrics['industry'] = yahoo_data.get('industry', metrics['industry'])
        metrics['country'] = yahoo_data.get('country', metrics['country'])
        
        # Financial metrics
        for field in ['market_cap', 'revenue', 'employees']:
            if yahoo_data.get(field) and not metrics.get(field):
                metrics[field] = yahoo_data.get(field)
        
        # Ratios
        for field in ['profit_margin', 'operating_margin', 'current_ratio']:
            if yahoo_data.get(field):
                metrics[field] = yahoo_data.get(field)
        
        if not metrics['data_source']:
            metrics['data_source'] = 'Yahoo Finance'
        else:
            metrics['data_source'] += ', Yahoo Finance'
    
    # Try MarketScreener as third source
    ms_data = scrape_marketscreener(symbol)
    if ms_data:
        for field in ['name', 'sector', 'industry', 'country', 'market_cap', 'revenue', 'net_income', 'pe_ratio']:
            if ms_data.get(field) and not metrics.get(field):
                metrics[field] = ms_data.get(field)
        
        if not metrics['data_source']:
            metrics['data_source'] = 'MarketScreener'
        else:
            metrics['data_source'] += ', MarketScreener'
    
    # Calculate derived metrics if possible
    if metrics['revenue'] and metrics['revenue'] > 0:
        # Profit margins
        if metrics['gross_profit']:
            metrics['gross_margin'] = round((metrics['gross_profit'] / metrics['revenue']) * 100, 2)
        if metrics['operating_income']:
            metrics['operating_margin'] = round((metrics['operating_income'] / metrics['revenue']) * 100, 2)
        if metrics['net_income']:
            metrics['net_margin'] = round((metrics['net_income'] / metrics['revenue']) * 100, 2)
    
    # Financial ratios
    if metrics['total_assets'] and metrics['total_assets'] > 0:
        metrics['roa'] = round((metrics['net_income'] / metrics['total_assets']) * 100, 2) if metrics['net_income'] else None
    
    if metrics['total_equity'] and metrics['total_equity'] > 0:
        metrics['roe'] = round((metrics['net_income'] / metrics['total_equity']) * 100, 2) if metrics['net_income'] else None
        metrics['debt_to_equity'] = round(metrics['total_liabilities'] / metrics['total_equity'], 2) if metrics['total_liabilities'] else None
    
    if metrics['current_assets'] and metrics['current_liabilities'] and metrics['current_liabilities'] > 0:
        metrics['current_ratio'] = round(metrics['current_assets'] / metrics['current_liabilities'], 2)
    
    return metrics

def update_financial_metrics(companies, max_companies=500):
    """Update financial metrics for companies in the database"""
    # Choose companies based on importance and data quality
    def importance_score(company):
        score = 0
        # Companies with complete core information are more valuable
        if (company.get('sector') and company['sector'] != 'Unknown' and 
            company.get('industry') and company['industry'] != 'Unknown'):
            score += 50
        
        # Companies with financial data are more important
        if company.get('market_cap') and company['market_cap'] > 0:
            score += 100
            # Larger companies are more important (log scale)
            if company['market_cap'] > 1_000_000_000:  # > $1B
                score += 50
            if company['market_cap'] > 10_000_000_000:  # > $10B
                score += 50
        
        # Companies with revenue are more likely to have good financials
        if company.get('revenue') and company['revenue'] > 0:
            score += 30
        
        # Prefer curated and European companies
        if company.get('source') == 'Curated List':
            score += 100
        if company.get('region') == 'Europe':
            score += 30
        
        return score
    
    sorted_companies = sorted(companies, key=importance_score, reverse=True)
    companies_to_update = sorted_companies[:max_companies]
    
    logger.info(f"Updating financial metrics for {len(companies_to_update)} companies")
    
    metrics_data = []
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # Submit tasks for processing
        future_to_company = {}
        for company in companies_to_update:
            symbol = company.get('symbol')
            future = executor.submit(fetch_financial_data, symbol)
            future_to_company[future] = company
        
        # Process results as they complete
        for future in tqdm(as_completed(future_to_company), total=len(future_to_company), desc="Updating metrics"):
            company = future_to_company[future]
            symbol = company.get('symbol')
            
            try:
                metrics = future.result()
                if metrics:
                    # Fill in missing data from the company info we already have
                    for field in ['name', 'sector', 'industry', 'country', 'market_cap', 'revenue', 'employees']:
                        if not metrics.get(field) and company.get(field) and company[field] != 'Unknown':
                            metrics[field] = company[field]
                    
                    metrics_data.append(metrics)
                else:
                    logger.warning(f"No metrics for {symbol}")
            except Exception as e:
                logger.error(f"Error updating metrics for {symbol}: {str(e)}")
    
    # Save metrics to CSV and JSON
    save_financial_metrics(metrics_data)
    
    return metrics_data

def save_company_database(companies):
    """Save the company database to CSV and JSON"""
    if not companies:
        logger.error("No companies to save")
        return
    
    # Convert to DataFrame
    df = pd.DataFrame(companies)
    
    # Clean up DataFrame (replace NaN with None for JSON serialization)
    df = df.replace({np.nan: None})
    
    # Save to CSV
    csv_path = os.path.join(DATA_DIR, f"company_database_{datetime.now().strftime('%Y%m%d')}.csv")
    df.to_csv(csv_path, index=False)
    logger.info(f"Saved company database to CSV: {csv_path}")
    
    # Save to JSON
    json_path = os.path.join(DATA_DIR, f"company_database_{datetime.now().strftime('%Y%m%d')}.json")
    with open(json_path, 'w') as f:
        json.dump(companies, f, indent=4)
    logger.info(f"Saved company database to JSON: {json_path}")
    
    # Create latest version links
    latest_csv = os.path.join(DATA_DIR, "company_database_latest.csv")
    latest_json = os.path.join(DATA_DIR, "company_database_latest.json")
    
    # Remove existing files if they exist
    if os.path.exists(latest_csv):
        os.remove(latest_csv)
    if os.path.exists(latest_json):
        os.remove(latest_json)
    
    # Copy the files to create the latest versions
    import shutil
    shutil.copy2(csv_path, latest_csv)
    shutil.copy2(json_path, latest_json)
    
    logger.info("Created latest version links")
    
    return df

def save_financial_metrics(metrics_data):
    """Save financial metrics to CSV and JSON"""
    if not metrics_data:
        logger.error("No metrics data to save")
        return
    
    # Convert to DataFrame
    metrics_df = pd.DataFrame(metrics_data)
    
    # Clean up DataFrame (replace NaN with None for JSON serialization)
    metrics_df = metrics_df.replace({np.nan: None})
    
    # Save to CSV
    csv_path = os.path.join(DATA_DIR, f"financial_metrics_{datetime.now().strftime('%Y%m%d')}.csv")
    metrics_df.to_csv(csv_path, index=False)
    logger.info(f"Saved financial metrics to CSV: {csv_path}")
    
    # Save to JSON
    json_path = os.path.join(DATA_DIR, f"financial_metrics_{datetime.now().strftime('%Y%m%d')}.json")
    with open(json_path, 'w') as f:
        json.dump(metrics_data, f, indent=4)
    logger.info(f"Saved financial metrics to JSON: {json_path}")
    
    # Update latest links
    latest_csv = os.path.join(DATA_DIR, "financial_metrics_latest.csv")
    latest_json = os.path.join(DATA_DIR, "financial_metrics_latest.json")
    
    if os.path.exists(latest_csv):
        os.remove(latest_csv)
    if os.path.exists(latest_json):
        os.remove(latest_json)
    
    import shutil
    shutil.copy2(csv_path, latest_csv)
    shutil.copy2(json_path, latest_json)
    
    logger.info("Created latest version links for financial metrics")
    
    return metrics_df

def create_unified_dataset():
    """
    Create a unified dataset that combines company database and financial metrics
    """
    company_file = os.path.join(DATA_DIR, "company_database_latest.csv")
    metrics_file = os.path.join(DATA_DIR, "financial_metrics_latest.csv")
    output_file = os.path.join(DATA_DIR, "unified_market_data.csv")
    
    if not os.path.exists(company_file) or not os.path.exists(metrics_file):
        logger.error("Cannot create unified dataset: missing input files")
        return None
    
    # Load the datasets
    companies = pd.read_csv(company_file)
    metrics = pd.read_csv(metrics_file)
    
    logger.info(f"Creating unified dataset from {len(companies)} companies and {len(metrics)} financial metrics")
    
    # Merge on symbol, keep all companies even if they don't have metrics
    unified = companies.merge(metrics, on='symbol', how='left', suffixes=('', '_metrics'))
    
    # Clean up duplicate columns
    # For each column that appears in both datasets, prefer the metrics version if available
    for col in unified.columns:
        if col.endswith('_metrics'):
            base_col = col.replace('_metrics', '')
            if base_col in unified.columns:
                # Fill missing values in the primary column with values from the metrics column
                unified[base_col] = unified[base_col].fillna(unified[col])
    
    # Drop the duplicate columns
    columns_to_drop = [col for col in unified.columns if col.endswith('_metrics')]
    unified = unified.drop(columns=columns_to_drop)
    
    # Save the unified dataset
    unified.to_csv(output_file, index=False)
    logger.info(f"Created unified dataset with {len(unified)} companies at {output_file}")
    
    return unified

def main():
    """
    Main function to run the market data scraper
    """
    logger.info("Starting market data scraper")
    
    try:
        # Step 1: Compile list of European companies from multiple sources
        logger.info("Compiling list of European companies...")
        european_companies = compile_european_companies()
        
        # Step 2: Gather detailed information for these companies
        logger.info("Gathering detailed company information...")
        # Increase max companies since we're using multiple data sources
        detailed_companies = gather_company_details(european_companies, max_companies=1000)
        
        # Step 3: Save the company database
        logger.info("Saving company database...")
        company_db = save_company_database(detailed_companies)
        
        # Step 4: Update financial metrics for top companies
        logger.info("Updating financial metrics for top companies...")
        # Increase max companies to get more complete financial data
        metrics_db = update_financial_metrics(detailed_companies, max_companies=500)
        
        # Step 5: Create a unified dataset
        logger.info("Creating unified dataset...")
        unified_db = create_unified_dataset()
        
        logger.info("Market data scraping completed successfully")
        
    except Exception as e:
        logger.error(f"Error in market data scraper: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        raise
    
    return {
        'company_db': os.path.join(DATA_DIR, "company_database_latest.csv"),
        'metrics_db': os.path.join(DATA_DIR, "financial_metrics_latest.csv"),
        'unified_db': os.path.join(DATA_DIR, "unified_market_data.csv")
    }

# def set_up_scheduled_task():
#     """
#     Set up a scheduled task to run the scraper weekly
#     This function creates a script that can be registered with the system's task scheduler
#     """
#     # Create a batch/shell script to run the scraper
#     script_dir = os.path.dirname(os.path.abspath(__file__))
    
#     if os.name == 'nt':  # Windows
#         script_path = os.path.join(script_dir, "run_market_scraper.bat")
#         with open(script_path, 'w') as f:
#             f.write('@echo off\n')
#             f.write(f'cd /d "{script_dir}"\n')
#             f.write(f'python -c "import market_data_scraper; market_data_scraper.main()"\n')
        
#         logger.info(f"Created Windows batch script: {script_path}")
#         logger.info("To schedule a weekly task, run the following command in Command Prompt as Administrator:")
#         logger.info(f'schtasks /create /tn "Market Data Scraper" /tr "{script_path}" /sc weekly /d SUN /st 00:00')
    
#     else:  # Linux/Mac
#         script_path = os.path.join(script_dir, "run_market_scraper.sh")
#         with open(script_path, 'w') as f:
#             f.write('#!/bin/bash\n')
#             f.write(f'cd "{script_dir}"\n')
#             f.write('python3 -c "import market_data_scraper; market_data_scraper.main()"\n')
        
#         # Make the script executable
#         os.chmod(script_path, 0o755)
        
#         logger.info(f"Created shell script: {script_path}")
#         logger.info("To schedule a weekly task, add the following line to your crontab (run 'crontab -e'):")
#         logger.info(f'0 0 * * 0 {script_path} >> {os.path.join(script_dir, "market_scraper.log")} 2>&1')
    
#     return script_path

if __name__ == "__main__":
    # If run directly, execute the main function
    main()