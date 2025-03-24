#!/usr/bin/env python
"""
Company Database Builder - Using Free APIs and Data Sources
----------------------------------------------------------
This script builds a database of public companies with their financial metrics
and industry classifications for use in competitor analysis.
"""

import os
import pandas as pd
import numpy as np
import json
import time
import random
import logging
import requests
from datetime import datetime
from bs4 import BeautifulSoup
import csv
import concurrent.futures

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger('CompanyDBBuilder')

def load_env_file(env_file='.env'):
    """
    Load environment variables from a .env file.
    """
    try:
        if os.path.exists(env_file):
            print(f"Loading environment variables from {env_file}")
            with open(env_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        key, value = line.split('=', 1)
                        os.environ[key] = value
            return True
        else:
            print(f"Environment file {env_file} not found")
            return False
    except Exception as e:
        print(f"Error loading environment file: {str(e)}")
        return False

# Load environment variables from .env file
load_env_file()

class CompanyDatabaseBuilder:
    def __init__(self, output_dir='./company_data'):
        """Initialize the database builder."""
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
        
        # Define the database path
        self.db_path = os.path.join(output_dir, 'company_database.csv')
        
        # Load existing database if available
        if os.path.exists(self.db_path):
            self.company_db = pd.read_csv(self.db_path)
            logger.info(f"Loaded existing database with {len(self.company_db)} companies")
        else:
            self.company_db = pd.DataFrame()
            logger.info("Starting new company database")
            
        # Track API usage to respect rate limits
        self.api_call_counts = {}
            
    def _respect_rate_limit(self, api_name, max_calls=50, time_window=60):
        """Implement rate limiting for API calls."""
        current_time = time.time()
        
        # Initialize tracking for this API if it doesn't exist
        if api_name not in self.api_call_counts:
            self.api_call_counts[api_name] = []
            
        # Remove calls outside the time window
        self.api_call_counts[api_name] = [
            t for t in self.api_call_counts[api_name] 
            if current_time - t < time_window
        ]
        
        # Check if we've exceeded the rate limit
        if len(self.api_call_counts[api_name]) >= max_calls:
            wait_time = time_window - (current_time - self.api_call_counts[api_name][0])
            print(f"Rate limit reached for {api_name}. Waiting {wait_time:.2f} seconds...")
            logger.warning(f"Rate limit reached for {api_name}. Waiting {wait_time:.2f} seconds")
            time.sleep(wait_time + 1)  # Add 1 second buffer
            return self._respect_rate_limit(api_name, max_calls, time_window)
            
        # Record this call
        self.api_call_counts[api_name].append(current_time)
        return True
    
    def download_marketstack_sample(self):
        """
        Download sample data from Marketstack's example responses.
        This is a free way to get some example company tickers.
        """
        print("Getting the initial list of companies...")
        logger.info("Getting sample tickers from Marketstack's documentation")
        
        tickers = [
            # European companies - Using common stock symbols
            {'symbol': 'BMW', 'name': 'Bayerische Motoren Werke AG', 'exchange': 'XETR', 'country': 'Germany'},
            {'symbol': 'SIE', 'name': 'Siemens AG', 'exchange': 'XETR', 'country': 'Germany'},
            {'symbol': 'SAP', 'name': 'SAP SE', 'exchange': 'XETR', 'country': 'Germany'},
            {'symbol': 'BAS', 'name': 'BASF SE', 'exchange': 'XETR', 'country': 'Germany'},
            {'symbol': 'ADS', 'name': 'Adidas AG', 'exchange': 'XETR', 'country': 'Germany'},
            {'symbol': 'AIR', 'name': 'Airbus SE', 'exchange': 'XPAR', 'country': 'France'},
            {'symbol': 'BNP', 'name': 'BNP Paribas', 'exchange': 'XPAR', 'country': 'France'},
            {'symbol': 'MC', 'name': 'LVMH Moet Hennessy Louis Vuitton SE', 'exchange': 'XPAR', 'country': 'France'},
            {'symbol': 'OR', 'name': 'L\'Oreal SA', 'exchange': 'XPAR', 'country': 'France'},
            {'symbol': 'SAN', 'name': 'Sanofi', 'exchange': 'XPAR', 'country': 'France'},
            {'symbol': 'ULVR', 'name': 'Unilever PLC', 'exchange': 'XLON', 'country': 'United Kingdom'},
            {'symbol': 'HSBA', 'name': 'HSBC Holdings PLC', 'exchange': 'XLON', 'country': 'United Kingdom'},
            {'symbol': 'BP', 'name': 'BP PLC', 'exchange': 'XLON', 'country': 'United Kingdom'},
            {'symbol': 'GSK', 'name': 'GSK PLC', 'exchange': 'XLON', 'country': 'United Kingdom'},
            {'symbol': 'AZN', 'name': 'AstraZeneca PLC', 'exchange': 'XLON', 'country': 'United Kingdom'},
            {'symbol': 'ASML', 'name': 'ASML Holding NV', 'exchange': 'XAMS', 'country': 'Netherlands'},
            {'symbol': 'INGA', 'name': 'ING Groep NV', 'exchange': 'XAMS', 'country': 'Netherlands'},
            {'symbol': 'AD', 'name': 'Koninklijke Ahold Delhaize NV', 'exchange': 'XAMS', 'country': 'Netherlands'},
            {'symbol': 'PHIA', 'name': 'Koninklijke Philips NV', 'exchange': 'XAMS', 'country': 'Netherlands'},
            {'symbol': 'NESN', 'name': 'Nestle SA', 'exchange': 'XSWX', 'country': 'Switzerland'},
            {'symbol': 'NOVN', 'name': 'Novartis AG', 'exchange': 'XSWX', 'country': 'Switzerland'},
            {'symbol': 'ROG', 'name': 'Roche Holding AG', 'exchange': 'XSWX', 'country': 'Switzerland'},
            {'symbol': 'IBE', 'name': 'Iberdrola SA', 'exchange': 'XMAD', 'country': 'Spain'},
            {'symbol': 'SAN', 'name': 'Banco Santander SA', 'exchange': 'XMAD', 'country': 'Spain'},
            {'symbol': 'TEF', 'name': 'Telefonica SA', 'exchange': 'XMAD', 'country': 'Spain'},
            {'symbol': 'BBVA', 'name': 'Banco Bilbao Vizcaya Argentaria SA', 'exchange': 'XMAD', 'country': 'Spain'},
            {'symbol': 'ISP', 'name': 'Intesa Sanpaolo SpA', 'exchange': 'XMIL', 'country': 'Italy'},
            {'symbol': 'ENI', 'name': 'Eni SpA', 'exchange': 'XMIL', 'country': 'Italy'},
            {'symbol': 'ENEL', 'name': 'Enel SpA', 'exchange': 'XMIL', 'country': 'Italy'},
            {'symbol': 'STLA', 'name': 'Stellantis NV', 'exchange': 'XMIL', 'country': 'Italy'},
        ]
        
        print(f"Found {len(tickers)} initial companies to process")
        
        # Save as DataFrame
        tickers_df = pd.DataFrame(tickers)
        tickers_df.to_csv(os.path.join(self.output_dir, 'initial_tickers.csv'), index=False)
        
        return tickers_df
    
    def get_company_data_from_alpha_vantage(self, ticker):
        """
        Get company information from Alpha Vantage API.
        Note: Free tier is limited to 5 API calls per minute, 500 per day.
        """
        # Get API key from environment variable
        api_key = os.environ.get("ALPHA_VANTAGE_API_KEY")
        
        if not api_key:
            print("No Alpha Vantage API key found. Set ALPHA_VANTAGE_API_KEY in your .env file")
            logger.warning("No Alpha Vantage API key found. Set ALPHA_VANTAGE_API_KEY in your .env file")
            return {}
        
        # Respect rate limits
        self._respect_rate_limit("alpha_vantage", max_calls=5, time_window=60)
        
        try:
            print(f"Getting data for {ticker} from Alpha Vantage...")
            # Call Alpha Vantage API for company overview
            url = f"https://www.alphavantage.co/query?function=OVERVIEW&symbol={ticker}&apikey={api_key}"
            response = requests.get(url)
            
            if response.status_code != 200:
                print(f"Failed to get data for {ticker}: HTTP {response.status_code}")
                logger.warning(f"Failed to get data for {ticker}: HTTP {response.status_code}")
                return {}
                
            data = response.json()
            
            # Check if we got valid data
            if not data or len(data) <= 1 or "Symbol" not in data:
                print(f"No valid data returned for {ticker}")
                logger.warning(f"No valid data returned for {ticker}")
                
                # Try alternate endpoints if company overview fails
                income_url = f"https://www.alphavantage.co/query?function=INCOME_STATEMENT&symbol={ticker}&apikey={api_key}"
                self._respect_rate_limit("alpha_vantage", max_calls=5, time_window=60)
                income_response = requests.get(income_url)
                
                if income_response.status_code == 200:
                    income_data = income_response.json()
                    if "annualReports" in income_data and len(income_data["annualReports"]) > 0:
                        latest_report = income_data["annualReports"][0]
                        return {
                            "revenue": float(latest_report.get("totalRevenue", 0)),
                            "income": float(latest_report.get("netIncome", 0)),
                            "profit_margin": float(latest_report.get("netIncome", 0)) / float(latest_report.get("totalRevenue", 1))
                        }
                return {}
                
            # Extract relevant information
            company_data = {
                "industry": data.get("Industry", ""),
                "sector": data.get("Sector", ""),
                "employees": int(data.get("FullTimeEmployees", 0)) if data.get("FullTimeEmployees") else None,
                "market_cap": float(data.get("MarketCapitalization", 0)) if data.get("MarketCapitalization") else None,
                "revenue": float(data.get("RevenueTTM", 0)) if data.get("RevenueTTM") else None,
                "income": float(data.get("GrossProfitTTM", 0)) if data.get("GrossProfitTTM") else None,
                "profit_margin": float(data.get("ProfitMargin", 0)) if data.get("ProfitMargin") else None,
                "description": data.get("Description", ""),
                "exchange": data.get("Exchange", ""),
                "country": data.get("Country", ""),
                "currency": data.get("Currency", "")
            }
            
            print(f"Successfully got data for {ticker}")
            return company_data
            
        except Exception as e:
            print(f"Error in Alpha Vantage API call for {ticker}: {str(e)}")
            logger.error(f"Error in Alpha Vantage API call for {ticker}: {str(e)}")
            return {}
    
    def get_company_data_from_yahoo(self, ticker, company_name):
        """
        Get company data through Yahoo Finance API.
        """
        try:
            # For European stocks, add the exchange suffix if needed
            exchange_mapping = {
                'XETR': '.DE',
                'XPAR': '.PA',
                'XLON': '.L',
                'XAMS': '.AS',
                'XMAD': '.MC',
                'XMIL': '.MI',
                'XSWX': '.SW'
            }
            
            print(f"Getting data for {company_name} from Yahoo Finance...")
            # Try to find correct Yahoo ticker
            search_url = f"https://query1.finance.yahoo.com/v1/finance/search?q={company_name}"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            
            response = requests.get(search_url, headers=headers)
            
            yahoo_ticker = None
            if response.status_code == 200:
                search_data = response.json()
                if 'quotes' in search_data and len(search_data['quotes']) > 0:
                    yahoo_ticker = search_data['quotes'][0]['symbol']
            
            if not yahoo_ticker:
                # Try with exchange suffix
                exchange_suffix = exchange_mapping.get(company_name.get('exchange', ''), '')
                yahoo_ticker = f"{ticker}{exchange_suffix}"
            
            # Get company statistics
            stats_url = f"https://query1.finance.yahoo.com/v10/finance/quoteSummary/{yahoo_ticker}?modules=summaryProfile,financialData,defaultKeyStatistics"
            stats_response = requests.get(stats_url, headers=headers)
            
            if stats_response.status_code != 200:
                print(f"Failed to get Yahoo data for {company_name}: HTTP {stats_response.status_code}")
                return {}
                
            stats_data = stats_response.json()
            if 'quoteSummary' not in stats_data or 'result' not in stats_data['quoteSummary'] or not stats_data['quoteSummary']['result']:
                print(f"No valid Yahoo data for {company_name}")
                return {}
                
            result = stats_data['quoteSummary']['result'][0]
            
            company_data = {}
            
            # Extract profile data
            if 'summaryProfile' in result:
                profile = result['summaryProfile']
                company_data['industry'] = profile.get('industry', '')
                company_data['sector'] = profile.get('sector', '')
                company_data['employees'] = profile.get('fullTimeEmployees', None)
                company_data['country'] = profile.get('country', '')
                company_data['description'] = profile.get('longBusinessSummary', '')
            
            # Extract financial data
            if 'financialData' in result:
                financial = result['financialData']
                company_data['revenue'] = financial.get('totalRevenue', {}).get('raw', None)
                company_data['profit_margin'] = financial.get('profitMargins', {}).get('raw', None)
            
            # Extract key statistics
            if 'defaultKeyStatistics' in result:
                stats = result['defaultKeyStatistics']
                company_data['market_cap'] = stats.get('marketCap', {}).get('raw', None)
            
            print(f"Successfully got Yahoo data for {company_name}")
            return company_data
            
        except Exception as e:
            print(f"Error getting Yahoo data for {company_name}: {str(e)}")
            logger.error(f"Error getting Yahoo data for {company_name}: {str(e)}")
            return {}
    
    def map_industry_to_sector(self, industry):
        """Map specific industry to broader sector."""
        if not industry or pd.isna(industry):
            return "Unknown"
            
        industry_lower = industry.lower()
        
        sector_mapping = {
            'technology': ['software', 'hardware', 'semiconductor', 'internet', 'technology', 'it services', 'electronics'],
            'healthcare': ['pharmaceutical', 'healthcare', 'medical', 'biotech', 'drug', 'hospital'],
            'consumer goods': ['retail', 'apparel', 'food', 'beverage', 'consumer', 'luxury', 'household'],
            'financials': ['bank', 'insurance', 'financial', 'real estate', 'investment', 'asset management'],
            'energy': ['oil', 'gas', 'energy', 'renewable', 'utility', 'power'],
            'industrials': ['industrial', 'manufacturing', 'aerospace', 'defense', 'engineering', 'construction'],
            'materials': ['chemical', 'mining', 'metal', 'material', 'paper', 'forestry'],
            'telecommunications': ['telecom', 'communications', 'wireless', 'media'],
            'transportation': ['airline', 'shipping', 'railroad', 'logistics', 'transportation']
        }
        
        for sector, keywords in sector_mapping.items():
            if any(keyword in industry_lower for keyword in keywords):
                return sector
                
        return "Other"
    
    def enrich_companies_from_free_sources(self, tickers_df):
        """
        Enrich company data using multiple free sources.
        Uses a combination of Alpha Vantage API and Yahoo Finance.
        """
        enriched_companies = []
        
        total_companies = len(tickers_df)
        print(f"\nStarting to enrich data for {total_companies} companies...")
        
        for idx, row in tickers_df.iterrows():
            ticker = row['symbol']
            company_name = row['name']
            exchange = row.get('exchange', '')
            
            print(f"\nProcessing {idx+1}/{total_companies}: {company_name} ({ticker})")
            logger.info(f"Enriching data for {company_name} ({ticker}) - {idx+1}/{len(tickers_df)}")
            
            company_data = {
                "ticker": ticker,
                "company_name": company_name,
                "exchange": exchange,
                "country": row.get('country', ''),
                "last_updated": datetime.now().strftime("%Y-%m-%d")
            }
            
            # Step 1: Try Alpha Vantage first (limited to 5 calls per minute)
            if idx % 5 == 0 and idx > 0:
                print("Pausing for Alpha Vantage rate limit...")
                logger.info("Pausing for Alpha Vantage rate limit...")
                time.sleep(60)  # Wait for rate limit reset
                
            alpha_data = self.get_company_data_from_alpha_vantage(ticker)
            if alpha_data:
                print(f"Got Alpha Vantage data for {company_name}")
                company_data.update(alpha_data)
            else:
                print(f"No Alpha Vantage data for {company_name}, trying Yahoo Finance...")
            
            # Step 2: If Alpha Vantage data is incomplete, try Yahoo Finance
            has_financials = ('revenue' in company_data and company_data['revenue'] and 
                             'industry' in company_data and company_data['industry'])
            
            if not has_financials:
                yahoo_data = self.get_company_data_from_yahoo(ticker, row)
                if yahoo_data:
                    print(f"Got Yahoo Finance data for {company_name}")
                    # Only update fields that are missing
                    for key, value in yahoo_data.items():
                        if (key not in company_data or not company_data[key]) and value:
                            company_data[key] = value
            
            # Step 3: Map industry to sector if we have industry but no sector
            if company_data.get('industry') and not company_data.get('sector'):
                company_data['sector'] = self.map_industry_to_sector(company_data['industry'])
            
            # Add to our enriched companies list
            enriched_companies.append(company_data)
            
            # Report progress
            if 'industry' in company_data and company_data['industry']:
                print(f"Industry: {company_data['industry']}")
            if 'revenue' in company_data and company_data['revenue']:
                print(f"Revenue: {company_data['revenue']/1000000:.2f}M")
            if 'employees' in company_data and company_data['employees']:
                print(f"Employees: {company_data['employees']}")
            
            # Save progress periodically
            if (idx + 1) % 5 == 0 or (idx + 1) == len(tickers_df):
                temp_df = pd.DataFrame(enriched_companies)
                temp_df.to_csv(os.path.join(self.output_dir, "enriched_companies_partial.csv"), index=False)
                print(f"Saved progress with {len(enriched_companies)} companies")
                logger.info(f"Saved progress with {len(enriched_companies)} companies")
        
        # Create final dataframe
        enriched_df = pd.DataFrame(enriched_companies)
        print(f"\nEnriched {len(enriched_df)} companies with data")
        
        # Check data completeness
        missing_revenue = enriched_df['revenue'].isna().sum()
        missing_industry = enriched_df['industry'].isna().sum()
        print(f"Companies missing revenue: {missing_revenue} ({missing_revenue/len(enriched_df)*100:.1f}%)")
        print(f"Companies missing industry: {missing_industry} ({missing_industry/len(enriched_df)*100:.1f}%)")
        
        return enriched_df
    
    def fill_missing_data(self, df):
        """
        Apply various strategies to fill missing data.
        """
        print("\nFilling missing data...")
        logger.info("Filling missing data in the database")
        
        # Copy to avoid modifying the original
        filled_df = df.copy()
        
        # 1. Fill sector based on industry
        if 'industry' in filled_df.columns and 'sector' in filled_df.columns:
            missing_sector_mask = filled_df['sector'].isna() & ~filled_df['industry'].isna()
            filled_df.loc[missing_sector_mask, 'sector'] = filled_df.loc[missing_sector_mask, 'industry'].apply(self.map_industry_to_sector)
            print(f"Filled sectors for {missing_sector_mask.sum()} companies")
        
        # 2. Financial metrics - use median by industry and size
        financial_cols = ['revenue', 'income', 'market_cap']
        for col in financial_cols:
            if col in filled_df.columns and filled_df[col].isna().any():
                missing_before = filled_df[col].isna().sum()
                # Group by sector and impute missing values with median
                filled_df[col] = filled_df.groupby('sector')[col].transform(
                    lambda x: x.fillna(x.median() if not pd.isna(x.median()) else 0)
                )
                missing_after = filled_df[col].isna().sum()
                print(f"Filled {missing_before - missing_after} missing values for {col}")
        
        # 3. Employees - fill based on revenue
        if 'employees' in filled_df.columns and 'revenue' in filled_df.columns and filled_df['employees'].isna().any():
            missing_before = filled_df['employees'].isna().sum()
            # Calculate revenue per employee for companies with both data points
            valid_mask = (~filled_df['employees'].isna()) & (~filled_df['revenue'].isna()) & (filled_df['employees'] > 0)
            if valid_mask.any():
                median_revenue_per_employee = (filled_df.loc[valid_mask, 'revenue'] / filled_df.loc[valid_mask, 'employees']).median()
                
                # Estimate employees from revenue
                missing_employees = filled_df['employees'].isna() & ~filled_df['revenue'].isna()
                filled_df.loc[missing_employees, 'employees'] = (
                    filled_df.loc[missing_employees, 'revenue'] / median_revenue_per_employee
                ).round().astype('Int64')
                
                missing_after = filled_df['employees'].isna().sum()
                print(f"Filled {missing_before - missing_after} missing employee counts")
        
        # 4. Fill profit margin if we have both revenue and income
        if 'profit_margin' in filled_df.columns and 'revenue' in filled_df.columns and 'income' in filled_df.columns:
            missing_before = filled_df['profit_margin'].isna().sum()
            missing_margin = filled_df['profit_margin'].isna() & ~filled_df['revenue'].isna() & ~filled_df['income'].isna() & (filled_df['revenue'] > 0)
            filled_df.loc[missing_margin, 'profit_margin'] = filled_df.loc[missing_margin, 'income'] / filled_df.loc[missing_margin, 'revenue']
            missing_after = filled_df['profit_margin'].isna().sum()
            print(f"Filled {missing_before - missing_after} missing profit margins")
        
        # 5. Fill any remaining NaNs with defaults
        for col in filled_df.columns:
            if filled_df[col].isna().any():
                missing_count = filled_df[col].isna().sum()
                if pd.api.types.is_numeric_dtype(filled_df[col]):
                    filled_df[col] = filled_df[col].fillna(0)
                else:
                    filled_df[col] = filled_df[col].fillna("Unknown")
                print(f"Filled {missing_count} remaining missing values for {col}")
        
        print("Completed filling missing data")
        return filled_df
    
    def generate_sample_data(self, num_companies=100):
        """
        Generate a sample database for demonstration purposes.
        This is used when API access is not available.
        """
        print(f"\nGenerating sample database with {num_companies} companies...")
        logger.info(f"Generating sample database with {num_companies} companies")
        
        # Define realistic ranges for each field
        industries = [
            'Software', 'Hardware', 'Banking', 'Insurance', 'Retail', 
            'Manufacturing', 'Healthcare', 'Energy', 'Telecommunications', 
            'Media', 'Food & Beverage', 'Pharmaceuticals', 'Transportation'
        ]
        
        sectors = [
            'Technology', 'Financial Services', 'Consumer Goods', 
            'Industrial', 'Healthcare', 'Energy', 'Communications', 'Materials'
        ]
        
        exchanges = ['XPAR', 'XLON', 'XETR', 'XAMS', 'XMAD', 'XMIL', 'XSWX', 'XBRU', 'XLIS', 'XOSL', 'XCSE']
        countries = ['France', 'UK', 'Germany', 'Netherlands', 'Spain', 'Italy', 'Switzerland', 'Belgium', 'Portugal', 'Norway', 'Denmark']
        
        companies = []
        for i in range(num_companies):
            # Progress indicator
            if (i+1) % 10 == 0:
                print(f"Generated {i+1}/{num_companies} sample companies...")
                
            # Generate random ticker symbol
            letters = ''.join(random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZ', k=random.randint(2, 4)))
            exchange = random.choice(exchanges)
            ticker = f"{letters}"
            
            # Assign country based on exchange
            country_mapping = {
                'XPAR': 'France', 'XLON': 'United Kingdom', 'XETR': 'Germany',
                'XAMS': 'Netherlands', 'XMAD': 'Spain', 'XMIL': 'Italy',
                'XSWX': 'Switzerland', 'XBRU': 'Belgium', 'XLIS': 'Portugal',
                'XOSL': 'Norway', 'XCSE': 'Denmark'
            }
            country = country_mapping.get(exchange, random.choice(countries))
            
            # Create random company
            industry = random.choice(industries)
            sector = self.map_industry_to_sector(industry)
            revenue = random.randint(1000000, 10000000000)  # Revenue between 1M and 10B
            market_cap = revenue * random.uniform(0.5, 5)   # Market cap as multiple of revenue
            employees = int(revenue / random.uniform(100000, 500000))  # Employees based on revenue
            profit_margin = random.uniform(-0.1, 0.3)       # Profit margin between -10% and 30%
            income = revenue * profit_margin
            
            company = {
                'ticker': ticker,
                'company_name': f"{random.choice(['Global', 'European', 'Tech', 'Digital', 'Advanced', 'Nordic', 'Alpine', 'Premier'])} {random.choice(['Solutions', 'Systems', 'Industries', 'Group', 'Partners', 'Enterprises', 'Corporation'])}",
                'exchange': exchange,
                'country': country,
                'industry': industry,
                'sector': sector,
                'employees': employees,
                'market_cap': market_cap,
                'revenue': revenue,
                'income': income,
                'profit_margin': profit_margin,
                'currency': 'EUR' if exchange != 'XLON' else 'GBP',
                'description': f"A leading {industry.lower()} company based in {country}.",
                'last_updated': datetime.now().strftime("%Y-%m-%d")
            }
            
            companies.append(company)
        
        # Create DataFrame
        sample_df = pd.DataFrame(companies)
        
        # Add some missing values to simulate real-world data
        for col in ['employees', 'market_cap', 'revenue', 'income']:
            # Randomly set 15% of values to NaN
            mask = np.random.random(len(sample_df)) < 0.15
            sample_df.loc[mask, col] = np.nan
        
        # Save sample data
        sample_df.to_csv(self.db_path, index=False)
        print(f"Sample database generated and saved to {self.db_path}")
        logger.info(f"Sample database generated and saved to {self.db_path}")
        
        return sample_df
    
    def build_database(self, use_alpha_vantage=True):
        """
        Main method to build the company database.
        
        Parameters:
        use_alpha_vantage (bool): Whether to use Alpha Vantage API (requires API key)
        """
        print("\n===== Building Company Database =====")
        logger.info("Starting company database build process")
        
        # Step 1: Get initial list of tickers
        print("\nStep 1: Getting initial list of companies...")
        logger.info("Getting initial list of companies")
        tickers_df = self.download_marketstack_sample()
        print(f"Initial list contains {len(tickers_df)} companies")
        
        # Step 2: Enrich with data from free sources
        print("\nStep 2: Enriching companies with financial and industry data...")
        if use_alpha_vantage:
            logger.info("Enriching company data using Alpha Vantage and other sources")
            enriched_df = self.enrich_companies_from_free_sources(tickers_df)
        else:
            print("Skipping API calls, generating sample data instead...")
            logger.info("Skipping Alpha Vantage API calls, generating sample data instead")
            enriched_df = self.generate_sample_data(len(tickers_df))
        
        # Step 3: Fill missing data
        print("\nStep 3: Filling missing data...")
        logger.info("Filling missing data")
        complete_df = self.fill_missing_data(enriched_df)
        
        # Save the final database
        print(f"\nSaving database with {len(complete_df)} companies...")
        logger.info(f"Saving database with {len(complete_df)} companies")
        complete_df.to_csv(self.db_path, index=False)
        self.company_db = complete_df
        
        # Create a timestamp file to track when the database was last updated
        with open(os.path.join(self.output_dir, "last_updated.txt"), "w") as f:
            f.write(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        
        print("\n===== Database Build Complete =====")
        print(f"Database saved to: {self.db_path}")
        print(f"Total companies: {len(complete_df)}")
        
        # Print data completeness statistics
        completeness = {col: (complete_df[col].notna().sum() / len(complete_df) * 100) 
                        for col in ['industry', 'sector', 'revenue', 'employees', 'market_cap', 'profit_margin']}
        
        print("\nData Completeness:")
        for col, pct in completeness.items():
            if col in complete_df.columns:
                print(f"- {col}: {pct:.1f}% complete")
        
        return complete_df
    

def main():
    """
    Main function to run the database builder.
    This will execute when the script is run directly.
    """
    print("\n=== Company Database Builder ===")
    print("This tool builds a database of European companies for competitor analysis")
    
    # Create output directory
    output_dir = "./company_data"
    os.makedirs(output_dir, exist_ok=True)
    
    # Initialize the database builder
    builder = CompanyDatabaseBuilder(output_dir=output_dir)
    
    # Check for Alpha Vantage API key
    api_key = os.environ.get("ALPHA_VANTAGE_API_KEY")
    if not api_key:
        print("\nNote: No Alpha Vantage API key found in environment variables.")
        print("Checking for .env file...")
        
        if os.path.exists('.env'):
            load_env_file()
            api_key = os.environ.get("ALPHA_VANTAGE_API_KEY")
            if api_key:
                print(f"Successfully loaded API key: {api_key[:4]}...{api_key[-4:]} from .env file")
            else:
                print("API key not found in .env file")
        else:
            print("No .env file found.")
            
        if not api_key:
            print("You can get a free API key at: https://www.alphavantage.co/support/#api-key")
            print("Then add it to a .env file with: ALPHA_VANTAGE_API_KEY=your_key_here")
    else:
        print(f"Using Alpha Vantage API key: {api_key[:4]}...{api_key[-4:]}")
    
    # Check if we already have a database
    db_path = os.path.join(output_dir, "company_database.csv")
    if os.path.exists(db_path):
        print(f"\nExisting database found at {db_path}")
        print("Options:")
        print("1. Use existing database")
        print("2. Rebuild database using API (Alpha Vantage + Yahoo Finance)")
        print("3. Generate new sample database (no API key needed)")
        
        choice = input("\nEnter your choice (1-3): ").strip()
        
        if choice == "1":
            print("Using existing database")
            company_db = pd.read_csv(db_path)
        elif choice == "2":
            print("Rebuilding database using APIs...")
            if not api_key:
                print("\nWarning: No Alpha Vantage API key found. Results may be limited.")
                proceed = input("Continue without API key? (y/n): ").strip().lower()
                if proceed != 'y':
                    print("Exiting. Please set an API key and try again.")
                    return
            company_db = builder.build_database(use_alpha_vantage=True)
        else:
            print("Generating sample database...")
            num_companies = input("How many sample companies? (default: 100): ").strip()
            num_companies = int(num_companies) if num_companies.isdigit() else 100
            company_db = builder.generate_sample_data(num_companies)
    else:
        print("\nNo existing database found.")
        print("Options:")
        print("1. Build database using API (Alpha Vantage + Yahoo Finance)")
        print("2. Generate sample database (no API key needed)")
        
        choice = input("\nEnter your choice (1-2): ").strip()
        
        if choice == "1":
            if not api_key:
                print("\nWarning: No Alpha Vantage API key found. Results may be limited.")
                proceed = input("Continue without API key? (y/n): ").strip().lower()
                if proceed != 'y':
                    print("Exiting. Please set an API key and try again.")
                    return
            
            print("Building database using APIs...")
            company_db = builder.build_database(use_alpha_vantage=True)
        else:
            print("Generating sample database...")
            num_companies = input("How many sample companies? (default: 100): ").strip()
            num_companies = int(num_companies) if num_companies.isdigit() else 100
            company_db = builder.generate_sample_data(num_companies)
    
    # Display database statistics
    if not company_db.empty:
        print("\n=== Database Statistics ===")
        print(f"Total companies: {len(company_db)}")
        
        # Count companies by country
        if 'country' in company_db.columns:
            country_counts = company_db['country'].value_counts().head(5)
            print("\nTop 5 Countries:")
            for country, count in country_counts.items():
                print(f"- {country}: {count} companies")
        
        # Count companies by sector
        if 'sector' in company_db.columns:
            sector_counts = company_db['sector'].value_counts().head(5)
            print("\nTop 5 Sectors:")
            for sector, count in sector_counts.items():
                print(f"- {sector}: {count} companies")
        
        # Revenue statistics
        if 'revenue' in company_db.columns:
            revenue_stats = company_db['revenue'].describe()
            print("\nRevenue Statistics (in millions):")
            print(f"- Min: {revenue_stats['min'] / 1000000:.2f}M")
            print(f"- Max: {revenue_stats['max'] / 1000000:.2f}M")
            print(f"- Average: {revenue_stats['mean'] / 1000000:.2f}M")
            print(f"- Median: {revenue_stats['50%'] / 1000000:.2f}M")
        
        # Data completeness
        print("\nData Completeness:")
        for column in ['industry', 'sector', 'employees', 'revenue', 'market_cap', 'profit_margin']:
            if column in company_db.columns:
                completeness = (company_db[column].notna().sum() / len(company_db)) * 100
                print(f"- {column}: {completeness:.1f}% complete")
        
        # Save sample as JSON for easier viewing
        sample_json_path = os.path.join(output_dir, "sample_companies.json")
        company_db.head(10).to_json(sample_json_path, orient="records", indent=2)
        print(f"\nSaved 10 sample companies to {sample_json_path} for easier viewing")
        
        print(f"\nFull database saved to {db_path}")
        print("\nThis database can now be used with the CompetitorMatcher class")
    else:
        print("Error: Database is empty")

if __name__ == "__main__":
    main()