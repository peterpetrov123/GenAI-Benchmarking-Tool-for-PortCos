import os
import time
import json
import logging
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import yfinance as yf
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv
import sys
from tqdm import tqdm
import random
from functools import wraps
from typing import Optional, Dict, Any

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

# Constants and paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(os.path.dirname(BASE_DIR), "financial_data", "market_data")
CACHE_DIR = os.path.join(DATA_DIR, "cache")
INPUT_CSV = os.path.join(DATA_DIR, "investpy_european_stocks.csv")
OUTPUT_CSV = os.path.join(DATA_DIR, "european_market_data_latest.csv")
MAX_WORKERS = 6  # Reduced to avoid rate limiting
REQUEST_DELAY = 0.5  # Increased base delay
MAX_RETRIES = 3
RETRY_DELAY = 1.5

# Enhanced country and exchange mappings
COUNTRY_SUFFIXES = {
    'United Kingdom': ['L', 'LON', 'IL'],
    'Germany': ['DE', 'F', 'BE', 'SG', 'MU', 'HM'],
    'France': ['PA', 'FP'],
    'Italy': ['MI', 'IM'],
    'Spain': ['MC', 'MA', 'SM'],
    'Netherlands': ['AS', 'NA', 'NL'],
    'Switzerland': ['SW', 'SWX', 'CH'],
    'Sweden': ['ST', 'STO', 'S'],
    'Belgium': ['BR', 'BB'],
    'Denmark': ['CO', 'CPH', 'DC'],
    'Finland': ['HE', 'HES', 'FH'],
    'Norway': ['OL', 'OSL', 'NO'],
    'Austria': ['VI', 'VIE', 'AV'],
    'Ireland': ['IR', 'QI'],
    'Portugal': ['LS', 'LIS'],
    'Greece': ['AT', 'ATG'],
    'Poland': ['WA', 'PW'],
    'Czech Republic': ['PR', 'PRA'],
    'Hungary': ['BD', 'BUD'],
    'Luxembourg': ['LX'],
    'Iceland': ['IC'],
}

EXCHANGE_COUNTRY_MAP = {
    **{suffix: country for country, suffixes in COUNTRY_SUFFIXES.items() for suffix in suffixes},
    'XETRA': 'Germany',
    'EPA': 'France',
    'AMS': 'Netherlands',
    'OSL': 'Norway',
    'CPH': 'Denmark',
    'WSE': 'Poland',
    'BSE': 'Bulgaria',
    'ISE': 'Ireland',
}

EUROPEAN_COUNTRIES = [
    'United Kingdom', 'Germany', 'France', 'Italy', 'Spain',
    'Netherlands', 'Switzerland', 'Sweden', 'Belgium', 'Denmark',
    'Finland', 'Norway', 'Austria', 'Ireland', 'Portugal', 'Greece',
    'Poland', 'Czech Republic', 'Hungary', 'Romania', 'Slovakia',
    'Luxembourg', 'Bulgaria', 'Croatia', 'Slovenia', 'Lithuania',
    'Latvia', 'Estonia', 'Cyprus', 'Malta', 'Iceland'
]

COUNTRY_CODE_MAP = {
    'UK': 'United Kingdom',
    'GB': 'United Kingdom',
    'DE': 'Germany',
    'FR': 'France',
    'IT': 'Italy',
    'ES': 'Spain',
    'NL': 'Netherlands',
    'CH': 'Switzerland',
    'SE': 'Sweden',
    'BE': 'Belgium',
    'DK': 'Denmark',
    'FI': 'Finland',
    'NO': 'Norway',
    'AT': 'Austria',
    'IE': 'Ireland',
    'PT': 'Portugal',
    'GR': 'Greece',
    'PL': 'Poland',
    'CZ': 'Czech Republic',
    'HU': 'Hungary',
    'RO': 'Romania',
    'SK': 'Slovakia',
    'LU': 'Luxembourg',
    'BG': 'Bulgaria',
    'HR': 'Croatia',
    'SI': 'Slovenia',
    'LT': 'Lithuania',
    'LV': 'Latvia',
    'EE': 'Estonia',
    'CY': 'Cyprus',
    'MT': 'Malta',
    'IS': 'Iceland'
}

# Retry decorator for Yahoo Finance requests
def retry_yfinance_request(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        for attempt in range(MAX_RETRIES):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                if attempt < MAX_RETRIES - 1:
                    sleep_time = RETRY_DELAY * (2 ** attempt) * (1 + random.random())
                    logger.warning(f"Retry {attempt + 1} for {args[0]} after error: {str(e)}")
                    time.sleep(sleep_time)
                    continue
                else:
                    raise
    return wrapper

def generate_symbol_variations(symbol: str, country: Optional[str] = None) -> list:
    """Generate multiple symbol variations for European stocks"""
    variations = []
    base_symbol = symbol.split('.')[0]
    
    # Original symbol first
    variations.append(symbol)
    
    # Country-specific suffixes
    if country:
        suffixes = COUNTRY_SUFFIXES.get(country, [])
        for suffix in suffixes:
            variations.append(f"{base_symbol}.{suffix}")
    
    # Common European variations
    variations.extend([
        f"{base_symbol}.EU",
        f"{base_symbol}.NX",
        f"{base_symbol}-EUR",
        f"{base_symbol}_",
        f"{base_symbol}-LN",
        f"{base_symbol}.BRU",
    ])
    
    # Exchange-specific variations
    variations.append(base_symbol)  # Try without suffix
    
    return list(set(variations))  # Remove duplicates

def validate_ticker_info(info: Dict[str, Any]) -> bool:
    """Validate if the ticker info contains sufficient data"""
    return bool(info and 'symbol' in info and info.get('quoteType') in ['EQUITY', 'ETF'])

@retry_yfinance_request
def get_ticker_with_retry(symbol: str) -> Optional[yf.Ticker]:
    """Get yfinance Ticker with retry logic"""
    time.sleep(REQUEST_DELAY * (1 + random.random()))
    ticker = yf.Ticker(symbol)
    try:
        # Force a small request to validate the ticker
        _ = ticker.isin
        return ticker
    except Exception:
        return None

def get_yfinance_data(symbol: str, row_data: Optional[Dict] = None) -> Dict[str, Any]:
    cache_file = os.path.join(CACHE_DIR, f"yf_{symbol.replace('^', '').replace('.', '_')}.json")
    
    # Try cache first
    if os.path.exists(cache_file):
        try:
            with open(cache_file, 'r') as f:
                cached_data = json.load(f)
                if datetime.now() - datetime.fromisoformat(cached_data['last_updated']) < timedelta(days=7):
                    return cached_data
        except Exception as e:
            logger.debug(f"Cache error for {symbol}: {e}")

    country = normalize_country(row_data.get('country')) if row_data else None
    symbol_variations = generate_symbol_variations(symbol, country)
    
    ticker = None
    valid_symbol = None
    for symbol_variant in symbol_variations:
        ticker = get_ticker_with_retry(symbol_variant)
        if ticker:
            info = ticker.info
            if validate_ticker_info(info):
                valid_symbol = symbol_variant
                logger.debug(f"Found valid symbol: {valid_symbol}")
                break
            time.sleep(0.2)
    
    if not ticker or not valid_symbol:
        logger.debug(f"No valid data found for {symbol} after {len(symbol_variations)} variations")
        return {'symbol': symbol, 'status': 'failed', 'last_updated': datetime.now().isoformat()}

    # Proceed with data extraction
    company_data = extract_financial_data(ticker, symbol, row_data)
    
    # Save to cache
    with open(cache_file, 'w') as f:
        json.dump(company_data, f)
    
    return company_data

def extract_financial_data(ticker: yf.Ticker, original_symbol: str, row_data: Dict) -> Dict[str, Any]:
    info = ticker.info
    company_data = {
        'symbol': original_symbol,
        'valid_symbol': ticker.ticker,
        'last_updated': datetime.now().isoformat(),
        'data_source': 'Yahoo Finance',
        'status': 'success',
    }
    
    # Basic Info
    basic_info = {
        'name': info.get('shortName', info.get('longName', row_data.get('name'))),
        'country': normalize_country(info.get('country', row_data.get('country'))),
        'sector': info.get('sector'),
        'industry': info.get('industry'),
        'exchange': info.get('exchange'),
        'currency': info.get('currency'),
        'market_cap': info.get('marketCap'),
        'website': info.get('website'),
        'employees': info.get('fullTimeEmployees'),
    }
    company_data.update({k: v for k, v in basic_info.items() if v})
    
    # Financial Ratios
    ratios = {
        'forward_pe': info.get('forwardPE'),
        'trailing_pe': info.get('trailingPE'),
        'peg_ratio': info.get('pegRatio'),
        'price_to_sales': info.get('priceToSalesTrailing12Months'),
        'price_to_book': info.get('priceToBook'),
        'enterprise_value': info.get('enterpriseValue'),
        'profit_margin': info.get('profitMargins'),
        'operating_margin': info.get('operatingMargins'),
        'return_on_equity': info.get('returnOnEquity'),
        'return_on_assets': info.get('returnOnAssets'),
    }
    company_data.update({k: v for k, v in ratios.items() if v is not None})
    
    # Financial Statements
    try:
        income_stmt = ticker.income_stmt.sort_index(axis=1, ascending=False)
        if not income_stmt.empty:
            recent_year = income_stmt.columns[0]
            revenue_keys = ['Total Revenue', 'Revenue', 'Operating Revenue']
            company_data.update({
                'revenue_annual': next((income_stmt.loc[k, recent_year] for k in revenue_keys if k in income_stmt.index), None),
                'net_income': income_stmt.loc['Net Income', recent_year] if 'Net Income' in income_stmt.index else None,
                'ebitda': income_stmt.loc['EBITDA', recent_year] if 'EBITDA' in income_stmt.index else None,
                'fiscal_year_end': recent_year.strftime('%Y-%m-%d'),
            })
    except Exception as e:
        logger.debug(f"Income statement error: {e}")

    try:
        balance_sheet = ticker.balance_sheet.sort_index(axis=1, ascending=False)
        if not balance_sheet.empty:
            recent_year = balance_sheet.columns[0]
            company_data.update({
                'total_assets': balance_sheet.loc['Total Assets', recent_year] if 'Total Assets' in balance_sheet.index else None,
                'total_debt': balance_sheet.loc['Total Debt', recent_year] if 'Total Debt' in balance_sheet.index else None,
                'total_equity': balance_sheet.loc['Total Equity Gross Minority Interest', recent_year] 
                               if 'Total Equity Gross Minority Interest' in balance_sheet.index else None,
                'cash': balance_sheet.loc['Cash And Cash Equivalents', recent_year] 
                      if 'Cash And Cash Equivalents' in balance_sheet.index else None,
            })
    except Exception as e:
        logger.debug(f"Balance sheet error: {e}")

    # Calculate derived metrics
    try:
        if company_data.get('total_debt') and company_data.get('total_equity'):
            company_data['debt_to_equity'] = company_data['total_debt'] / company_data['total_equity']
        if company_data.get('current_assets') and company_data.get('current_liabilities'):
            company_data['current_ratio'] = company_data['current_assets'] / company_data['current_liabilities']
    except Exception as e:
        logger.debug(f"Ratio calculation error: {e}")

    # Final validation
    required_fields = ['name', 'sector', 'country', 'market_cap']
    if not all(company_data.get(f) for f in required_fields):
        company_data['status'] = 'incomplete'
    
    return company_data

# Remaining functions (process_all_companies, process_company_batch, filter_and_save_results, main) 
# remain similar but use the updated get_yfinance_data and validation checks
def is_european_country(country: Optional[str]) -> bool:
    """Check if a country is European with enhanced validation"""
    if not country or country == 'Unknown':
        return False
    
    # Normalize the country name first
    normalized = normalize_country(country)
    
    # Check against official European countries list
    if normalized in EUROPEAN_COUNTRIES:
        return True
    
    # Check country code mappings
    if country.upper() in COUNTRY_CODE_MAP:
        return True
    
    # Check exchange-based country mappings
    if normalized in EXCHANGE_COUNTRY_MAP.values():
        return True
    
    # Check if any European country name is contained in the input
    for euro_country in EUROPEAN_COUNTRIES:
        if euro_country.lower() in country.lower():
            return True
    
    return False

# Update the EXCHANGE_COUNTRY_MAP to include more entries
EXCHANGE_COUNTRY_MAP = {
    **{suffix: country for country, suffixes in COUNTRY_SUFFIXES.items() for suffix in suffixes},
    'LSE': 'United Kingdom',
    'FRA': 'Germany',
    'EPA': 'France',
    'MIL': 'Italy',
    'MAD': 'Spain',
    'AMS': 'Netherlands',
    'SWX': 'Switzerland',
    'STO': 'Sweden',
    'OSL': 'Norway',
    'CPH': 'Denmark',
    'HEL': 'Finland',
    'VSE': 'Austria',
    'DUB': 'Ireland',
    'LIS': 'Portugal',
    'ATH': 'Greece',
    'WSE': 'Poland',
    'PSE': 'Czech Republic',
    'BSE': 'Bulgaria',
    'ISE': 'Ireland',
    'RSE': 'Romania'
}

# Update the normalize_country function to use all mappings
def normalize_country(country: Optional[str]) -> str:
    """Normalize country names using multiple data sources"""
    if not country or pd.isna(country):
        return 'Unknown'
    
    # Clean input
    country = str(country).strip().title()
    
    # 1. Check country codes
    if country.upper() in COUNTRY_CODE_MAP:
        return COUNTRY_CODE_MAP[country.upper()]
    
    # 2. Check exchange suffixes
    if '.' in country:
        suffix = country.split('.')[-1]
        if suffix in EXCHANGE_COUNTRY_MAP:
            return EXCHANGE_COUNTRY_MAP[suffix]
    
    # 3. Check full country names
    for euro_country in EUROPEAN_COUNTRIES:
        if euro_country.lower() == country.lower():
            return euro_country
        if euro_country.lower() in country.lower():
            return euro_country
    
    # 4. Check partial matches in exchange map values
    for name in EXCHANGE_COUNTRY_MAP.values():
        if name.lower() in country.lower():
            return name
    
    # 5. Check special cases
    special_cases = {
        'UK': 'United Kingdom',
        'GREAT BRITAIN': 'United Kingdom',
        'DEUTSCHLAND': 'Germany',
        'ÖSTERREICH': 'Austria',
        'SUISSE': 'Switzerland'
    }
    for key, value in special_cases.items():
        if key.lower() in country.lower():
            return value
    
    return 'Unknown'

def process_company_batch(companies_df):
    """Process companies with enhanced validation"""
    results = []
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_symbol = {}
        for _, row in companies_df.iterrows():
            future = executor.submit(get_yfinance_data, row['symbol'], row.to_dict())
            future_to_symbol[future] = row['symbol']
        
        for future in tqdm(as_completed(future_to_symbol), total=len(future_to_symbol), desc="Processing"):
            symbol = future_to_symbol[future]
            try:
                result = future.result()
                if result.get('status') == 'success' and is_european_country(result.get('country')):
                    results.append(result)
            except Exception as e:
                logger.error(f"Failed processing {symbol}: {str(e)}")
    
    logger.info(f"Processed {len(results)} valid companies")
    return results

# Other helper functions remain largely the same with minor adjustments for data validation
# ... (keep all previous imports and constants from the improved version)

def normalize_country(country: Optional[str]) -> str:
    """Normalize country names to standard format with enhanced matching"""
    if not country or pd.isna(country):
        return 'Unknown'
    
    # Clean input
    country = str(country).strip().title()
    
    # Check country codes first
    if country.upper() in COUNTRY_CODE_MAP:
        return COUNTRY_CODE_MAP[country.upper()]
    
    # Check direct mappings
    for standard_name, variants in COUNTRY_SUFFIXES.items():
        if country.lower() in [v.lower() for v in variants]:
            return standard_name
        if any(word in country.lower() for word in standard_name.lower().split()):
            return standard_name
    
    # Check partial matches in European countries list
    for euro_country in EUROPEAN_COUNTRIES:
        euro_lower = euro_country.lower()
        if euro_lower in country.lower():
            if euro_country in ['UK', 'Great Britain', 'England', 'Scotland', 'Wales']:
                return 'United Kingdom'
            return euro_country
    
    # Check exchange mappings
    for suffix, standard_name in EXCHANGE_COUNTRY_MAP.items():
        if suffix.lower() in country.lower():
            return standard_name
    
    return 'Unknown'

def process_all_companies(input_csv: str, batch_size: Optional[int] = None, 
                         max_companies: Optional[int] = None) -> list:
    """
    Process companies from input CSV with enhanced validation
    """
    try:
        stocks_df = pd.read_csv(input_csv)
        logger.info(f"Loaded {len(stocks_df)} companies from {input_csv}")
        
        # Pre-filter European companies
        if 'country' in stocks_df.columns:
            stocks_df['country'] = stocks_df['country'].apply(normalize_country)
            european_mask = stocks_df['country'].apply(lambda c: c != 'Unknown')
            stocks_df = stocks_df[european_mask].copy()
            logger.info(f"Filtered to {len(stocks_df)} European companies")
        
        if max_companies and len(stocks_df) > max_companies:
            stocks_df = stocks_df.sample(max_companies, random_state=42)
            logger.info(f"Sampled {max_companies} companies")
        
        results = []
        if batch_size:
            batches = np.array_split(stocks_df, max(1, len(stocks_df)//batch_size))
            for batch_num, batch_df in enumerate(batches, 1):
                logger.info(f"Processing batch {batch_num}/{len(batches)}")
                batch_results = process_company_batch(batch_df)
                results.extend(batch_results)
                save_interim_results(results, batch_num)
        else:
            results = process_company_batch(stocks_df)
        
        return results
    except Exception as e:
        logger.error(f"Error in process_all_companies: {e}")
        return []

def save_interim_results(results: list, batch_num: int):
    """Save interim results with validation"""
    if not results:
        return
    
    valid_results = [r for r in results if r.get('status') == 'success']
    df = pd.DataFrame(valid_results)
    
    interim_file = os.path.join(DATA_DIR, f"interim_batch_{batch_num}_{datetime.now().strftime('%Y%m%d')}.csv")
    df.to_csv(interim_file, index=False)
    logger.info(f"Saved interim batch {batch_num} with {len(df)} valid companies")

def process_company_batch(companies_df: pd.DataFrame) -> list:
    """Process a batch of companies with enhanced parallel processing"""
    results = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = []
        for _, row in companies_df.iterrows():
            futures.append(executor.submit(
                get_yfinance_data, 
                symbol=row['symbol'], 
                row_data=row.to_dict()
            ))
        
        with tqdm(total=len(futures), desc="Processing Companies") as pbar:
            for future in as_completed(futures):
                try:
                    result = future.result()
                    if result.get('status') == 'success' and is_european_country(result.get('country')):
                        results.append(result)
                except Exception as e:
                    logger.error(f"Processing failed: {e}")
                finally:
                    pbar.update(1)
    
    logger.info(f"Completed batch with {len(results)} valid entries")
    return results

def filter_and_save_results(results: list):
    """Save results with comprehensive quality filtering"""
    if not results:
        logger.error("No results to save")
        return
    
    df = pd.DataFrame(results)
    
    # Quality filtering
    df = df[df['status'] == 'success']
    df = df.drop(columns=['status'])
    
    # Calculate data completeness
    essential_cols = ['name', 'sector', 'country', 'market_cap', 'revenue_annual']
    df['completeness'] = df[essential_cols].notna().mean(axis=1)
    
    # Filter and sort
    complete_df = df[df['completeness'] >= 0.7].sort_values('market_cap', ascending=False)
    partial_df = df[(df['completeness'] >= 0.4) & (df['completeness'] < 0.7)]
    
    # Save full dataset
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    full_path = os.path.join(DATA_DIR, f"european_companies_full_{timestamp}.csv")
    df.to_csv(full_path, index=False)
    
    # Save high-quality subset
    hq_path = os.path.join(DATA_DIR, f"european_companies_hq_{timestamp}.csv")
    complete_df.to_csv(hq_path, index=False)
    
    # Save partial results
    partial_path = os.path.join(DATA_DIR, f"european_companies_partial_{timestamp}.csv")
    partial_df.to_csv(partial_path, index=False)
    
    logger.info(f"""
    Saved results:
    - Full dataset ({len(df)} entries): {full_path}
    - High-quality ({len(complete_df)} entries): {hq_path}
    - Partial ({len(partial_df)} entries): {partial_path}
    """)
    
    return {
        'full': full_path,
        'high_quality': hq_path,
        'partial': partial_path
    }

def main():
    """Enhanced main function with progress tracking"""
    logger.info("Starting European Market Data Collector")
    
    if not os.path.exists(INPUT_CSV):
        logger.error(f"Input file missing: {INPUT_CSV}")
        return
    
    try:
        # Process with batch size and max companies for testing
        results = process_all_companies(
            input_csv=INPUT_CSV,
            batch_size=200,  # Process 200 companies at a time
            max_companies=2000  # Limit total for testing
        )
        
        if not results:
            logger.warning("No valid results obtained")
            return
        
        # Save and filter results
        output_paths = filter_and_save_results(results)
        
        logger.info(f"Processing complete. High-quality data saved to {output_paths['high_quality']}")
        
    except KeyboardInterrupt:
        logger.info("Process interrupted by user")
    except Exception as e:
        logger.error(f"Critical error in main: {e}")
    finally:
        logger.info("Cleaning up resources")

if __name__ == "__main__":
    main()