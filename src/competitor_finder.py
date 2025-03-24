import os
import json
import pandas as pd
import requests
from bs4 import BeautifulSoup
import time
import re
import logging
import yfinance as yf
from dotenv import load_dotenv
import nltk
from nltk.corpus import stopwords
from collections import defaultdict

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Set up NLTK
try:
    stopwords.words('english')
except:
    nltk.download('stopwords', quiet=True)

class CompetitorFinder:
    """Finds similar companies for benchmarking based on industry, size, and region"""
    
    def __init__(self, financial_data_dir=None):
        """Initialize the CompetitorFinder with paths"""
        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        
        if financial_data_dir is None:
            self.financial_data_dir = os.path.join(os.path.dirname(self.base_dir), "financial_data")
        else:
            self.financial_data_dir = financial_data_dir
            
        # Create cache directory for company data
        self.cache_dir = os.path.join(self.financial_data_dir, "company_data_cache")
        os.makedirs(self.cache_dir, exist_ok=True)
        
        # Initialize company database
        self.company_database = None
        
    def extract_company_info(self, pdf_data_path=None, company_name=None):
        """
        Extract company information from the processed financial data
        or use provided company name to lookup information
        """
        company_info = {
            "name": company_name,
            "industry": None,
            "sub_industry": None,
            "region": None,
            "country": None,
            "revenue": None,
            "employees": None
        }
        
        if pdf_data_path and os.path.exists(pdf_data_path):
            # Load the processed PDF data (output from azure_processing.py)
            logger.info(f"Loading processed financial data from: {pdf_data_path}")
            try:
                with open(pdf_data_path, 'r') as f:
                    pdf_data = json.load(f)
                
                # Extract company information from the processed data
                # This assumes a certain structure in the JSON output from azure_processing.py
                
                if 'company' in pdf_data:
                    company_info['name'] = pdf_data.get('company', company_name)
                
                # Try to extract industry information
                if 'industry' in pdf_data:
                    company_info['industry'] = pdf_data['industry']
                else:
                    # Look through KPIs or metadata for industry information
                    for section in ['metadata', 'financial_data', 'kpis']:
                        if section in pdf_data and isinstance(pdf_data[section], dict):
                            if 'industry' in pdf_data[section]:
                                company_info['industry'] = pdf_data[section]['industry']
                                break
                
                # Try to extract location/region information
                for field in ['region', 'country', 'location']:
                    if field in pdf_data:
                        if field == 'location':
                            company_info['country'] = pdf_data[field]
                        else:
                            company_info[field] = pdf_data[field]
                
                # Try to extract revenue information
                revenue_keys = ['revenue', 'total_revenue', 'annual_revenue']
                for key in revenue_keys:
                    if key in pdf_data:
                        company_info['revenue'] = self._parse_financial_value(pdf_data[key])
                        break
                
                # Try to extract employee count
                employee_keys = ['employees', 'employee_count', 'workforce']
                for key in employee_keys:
                    if key in pdf_data:
                        company_info['employees'] = self._parse_financial_value(pdf_data[key])
                        break
            
            except Exception as e:
                logger.error(f"Error extracting company info from processed data: {str(e)}")
        
        # If we don't have a company name yet, try to extract from the filename
        if not company_info['name'] and pdf_data_path:
            filename = os.path.basename(pdf_data_path)
            company_name = re.sub(r'[_\.]', ' ', os.path.splitext(filename)[0])
            company_info['name'] = company_name
        
        # If we still don't have industry information, infer it from the company name
        if company_info['name'] and not company_info['industry']:
            company_info['industry'] = self._infer_industry(company_info['name'])
            logger.info(f"Inferred industry from name: {company_info['industry']}")
        
        return company_info
    
    def _parse_financial_value(self, value):
        """Parse financial values from different formats to numeric"""
        if isinstance(value, (int, float)):
            return value
            
        if isinstance(value, str):
            # Remove currency symbols, commas, and other non-numeric characters
            clean_value = re.sub(r'[^\d.]', '', value)
            try:
                return float(clean_value)
            except:
                pass
                
            # Handle values with million/billion indicators
            multipliers = {'k': 1000, 'm': 1000000, 'b': 1000000000}
            for suffix, multiplier in multipliers.items():
                if suffix in value.lower():
                    clean_value = re.sub(r'[^\d.]', '', value.lower().split(suffix)[0])
                    try:
                        return float(clean_value) * multiplier
                    except:
                        pass
        
        return None
    
    def _infer_industry(self, company_name):
        """Infer company industry from its name"""
        if not company_name:
            return "Unknown"
            
        # Common industry keywords
        industry_keywords = {
            "Healthcare": ["health", "medical", "hospital", "clinic", "care"],
            "Pharmaceuticals": ["pharma", "drug", "biotech", "therapeutic", "medicines"],
            "Technology": ["tech", "software", "digital", "cyber", "systems", "IT", "stream", "computing"],
            "Financial Services": ["bank", "finance", "invest", "capital", "financial", "asset"],
            "Energy": ["energy", "oil", "gas", "solar", "power", "renewable"],
            "Manufacturing": ["manufacturing", "industrial", "factory", "product", "fabrication"],
            "Retail": ["retail", "store", "shop", "mart", "market", "consumer"],
            "Telecommunications": ["telecom", "communication", "network", "mobile", "wireless"],
            "Real Estate": ["property", "real estate", "realty", "construction", "building"],
            "Transportation": ["transport", "logistics", "shipping", "delivery", "freight"],
            "Media & Entertainment": ["media", "entertainment", "film", "game", "broadcast", "production", "music", "streaming"]
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
    
    def load_company_database(self, rebuild=False):
        """
        Load the company database from cache or external sources
        
        Args:
            rebuild (bool): Force rebuilding the database even if cached version exists
        """
        cache_file = os.path.join(self.cache_dir, "company_database.csv")
        
        # Try to load from cache first if not rebuilding
        if os.path.exists(cache_file) and not rebuild:
            logger.info("Loading company database from cache...")
            self.company_database = pd.read_csv(cache_file)
            logger.info(f"Loaded {len(self.company_database)} companies from cache")
            return self.company_database
        
        # If not in cache or rebuilding, create from external sources
        logger.info("Building European company database from external sources...")
        
        # Initialize an empty database
        all_companies = self._fetch_european_companies()
        
        # If we got companies, convert to DataFrame and save
        if all_companies:
            self.company_database = pd.DataFrame(all_companies)
            
            # Save to cache
            os.makedirs(os.path.dirname(cache_file), exist_ok=True)
            self.company_database.to_csv(cache_file, index=False)
            logger.info(f"Saved {len(self.company_database)} European companies to cache")
            
            return self.company_database
        
        # If we couldn't get companies but have a cached version, use that
        if os.path.exists(cache_file):
            logger.warning("Failed to fetch new data. Using cached company database.")
            self.company_database = pd.read_csv(cache_file)
            return self.company_database
            
        # If all else fails, create a minimal sample for Europe
        logger.warning("No data could be fetched and no cache exists. Creating a minimal European sample.")
        self.company_database = self._create_minimal_european_dataset()
        self.company_database.to_csv(cache_file, index=False)
        
        return self.company_database
    
    def _fetch_european_companies(self):
        """Fetch European company data from multiple sources"""
        all_companies = []
        
        # Try different approaches to get European companies
        
        # 1. First try direct European stock screening using major European indices
        euro_companies = self._fetch_major_european_indices()
        if euro_companies:
            all_companies.extend(euro_companies)
            logger.info(f"Fetched {len(euro_companies)} companies from European indices")
        
        # 2. Try hardcoded top European companies if we don't have many yet
        if len(all_companies) < 50:
            top_euro_companies = self._get_top_european_companies()
            all_companies.extend(top_euro_companies)
            logger.info(f"Added {len(top_euro_companies)} top European companies")
        
        # Return whatever we've managed to collect
        logger.info(f"Total European companies collected: {len(all_companies)}")
        return all_companies
    
    def _fetch_major_european_indices(self):
        """Fetch company data from major European stock indices"""
        companies = []
        
        # Major European indices to try
        indices = {
            "^FTSE": "UK", # FTSE 100 (UK)
            "^GDAXI": "Germany", # DAX (Germany)
            "^FCHI": "France", # CAC 40 (France)
            "^STOXX50E": "Europe", # Euro Stoxx 50
            "^IBEX": "Spain", # IBEX 35 (Spain)
            "^OMX": "Sweden", # OMX Stockholm 30
            "^SSMI": "Switzerland", # Swiss Market Index
        }
        
        for index, country in indices.items():
            try:
                # Get the index components
                ticker = yf.Ticker(index)
                
                # For some indices we can get components directly
                if hasattr(ticker, 'components'):
                    components = ticker.components
                else:
                    # Manually look up some known components for major indices
                    components = self._get_known_index_components(index)
                
                # Process each component
                for symbol in components[:20]:  # Limit to top 20 from each index
                    try:
                        # Get company info
                        company_ticker = yf.Ticker(symbol)
                        info = company_ticker.info
                        
                        # Skip if we couldn't get basic info
                        if not info or 'shortName' not in info:
                            continue
                        
                        company = {
                            'symbol': symbol,
                            'name': info.get('shortName', info.get('longName', symbol)),
                            'industry': info.get('industry', 'Unknown'),
                            'sector': info.get('sector', 'Unknown'),
                            'country': info.get('country', country),
                            'region': 'Europe',
                            'revenue': info.get('totalRevenue', None),
                            'employees': info.get('fullTimeEmployees', None),
                            'market_cap': info.get('marketCap', None)
                        }
                        
                        companies.append(company)
                        logger.info(f"Added {company['name']} ({symbol}) - {company['industry']} - {company['country']}")
                        
                        # Small delay to avoid rate limiting
                        time.sleep(0.2)
                        
                    except Exception as e:
                        logger.warning(f"Error fetching data for {symbol}: {str(e)}")
                
            except Exception as e:
                logger.warning(f"Error fetching data for index {index}: {str(e)}")
        
        return companies
    
    def _get_known_index_components(self, index):
        """Get known components for major European indices"""
        # Simplified components for major indices
        components = {
            "^FTSE": ["BP.L", "HSBA.L", "GSK.L", "ULVR.L", "RIO.L", "SHEL.L", "BATS.L", "AZN.L", "LLOY.L", "VOD.L"],
            "^GDAXI": ["SAP.DE", "SIE.DE", "ALV.DE", "BAS.DE", "BMW.DE", "BAY.DE", "DTE.DE", "DBK.DE", "HEN.DE", "ADS.DE"],
            "^FCHI": ["BNP.PA", "MC.PA", "SAN.PA", "AIR.PA", "OR.PA", "CS.PA", "RI.PA", "EN.PA", "EL.PA", "ML.PA"],
            "^STOXX50E": ["ASML.AS", "SAP.DE", "LVMH.PA", "SIE.DE", "TOT.PA", "SAN.MC", "AIR.PA", "ALV.DE", "ENI.MI", "ENEL.MI"],
            "^IBEX": ["SAN.MC", "ITX.MC", "BBVA.MC", "IBE.MC", "REP.MC", "TEF.MC", "AMS.MC", "ELE.MC", "FER.MC", "MAP.MC"],
            "^OMX": ["ATCO-A.ST", "AZN.ST", "ERIC-B.ST", "HM-B.ST", "VOLV-B.ST", "NDA-SE.ST", "SEB-A.ST", "SAND.ST", "SWED-A.ST", "INVE-B.ST"],
            "^SSMI": ["NESN.SW", "ROG.SW", "NOVN.SW", "UHR.SW", "ABBN.SW", "SREN.SW", "ZURN.SW", "CS.SW", "HOLN.SW", "GIVN.SW"]
        }
        
        return components.get(index, [])
    
    def _get_top_european_companies(self):
        """Hardcoded list of top European companies with basic data"""
        # Top European companies from different sectors and countries
        companies = [
            {
                'symbol': 'ASML.AS',
                'name': 'ASML Holding',
                'industry': 'Semiconductor Equipment & Materials',
                'sector': 'Technology',
                'country': 'Netherlands',
                'region': 'Europe',
                'revenue': 21173000000,
                'employees': 30000,
                'market_cap': 300000000000
            },
            {
                'symbol': 'SAP.DE',
                'name': 'SAP SE',
                'industry': 'Software—Application',
                'sector': 'Technology',
                'country': 'Germany',
                'region': 'Europe',
                'revenue': 30000000000,
                'employees': 107000,
                'market_cap': 180000000000
            },
            {
                'symbol': 'LVMH.PA',
                'name': 'LVMH Moët Hennessy Louis Vuitton',
                'industry': 'Luxury Goods',
                'sector': 'Consumer Cyclical',
                'country': 'France',
                'region': 'Europe',
                'revenue': 79000000000,
                'employees': 175000,
                'market_cap': 400000000000
            },
            {
                'symbol': 'NESN.SW',
                'name': 'Nestlé S.A.',
                'industry': 'Packaged Foods',
                'sector': 'Consumer Defensive',
                'country': 'Switzerland',
                'region': 'Europe',
                'revenue': 95000000000,
                'employees': 275000,
                'market_cap': 300000000000
            },
            {
                'symbol': 'NOVOB.CO',
                'name': 'Novo Nordisk A/S',
                'industry': 'Biotechnology',
                'sector': 'Healthcare',
                'country': 'Denmark',
                'region': 'Europe',
                'revenue': 20000000000,
                'employees': 45000,
                'market_cap': 350000000000
            },
            {
                'symbol': 'AZN.L',
                'name': 'AstraZeneca PLC',
                'industry': 'Drug Manufacturers—General',
                'sector': 'Healthcare',
                'country': 'United Kingdom',
                'region': 'Europe',
                'revenue': 45000000000,
                'employees': 83000,
                'market_cap': 210000000000
            },
            {
                'symbol': 'SAN.MC',
                'name': 'Banco Santander, S.A.',
                'industry': 'Banks—Diversified',
                'sector': 'Financial Services',
                'country': 'Spain',
                'region': 'Europe',
                'revenue': 60000000000,
                'employees': 200000,
                'market_cap': 65000000000
            },
            {
                'symbol': 'SHEL.L',
                'name': 'Shell plc',
                'industry': 'Oil & Gas Integrated',
                'sector': 'Energy',
                'country': 'United Kingdom',
                'region': 'Europe',
                'revenue': 380000000000,
                'employees': 93000,
                'market_cap': 220000000000
            },
            {
                'symbol': 'SIE.DE',
                'name': 'Siemens AG',
                'industry': 'Specialty Industrial Machinery',
                'sector': 'Industrials',
                'country': 'Germany',
                'region': 'Europe',
                'revenue': 72000000000,
                'employees': 300000,
                'market_cap': 130000000000
            },
            {
                'symbol': 'ERICb.ST',
                'name': 'Telefonaktiebolaget LM Ericsson',
                'industry': 'Communication Equipment',
                'sector': 'Technology',
                'country': 'Sweden',
                'region': 'Europe',
                'revenue': 25000000000,
                'employees': 100000,
                'market_cap': 20000000000
            },
            {
                'symbol': 'NOKIA.HE',
                'name': 'Nokia Oyj',
                'industry': 'Communication Equipment',
                'sector': 'Technology',
                'country': 'Finland',
                'region': 'Europe',
                'revenue': 22500000000,
                'employees': 86000,
                'market_cap': 25000000000
            },
            {
                'symbol': 'BMW.DE',
                'name': 'Bayerische Motoren Werke AG',
                'industry': 'Auto Manufacturers',
                'sector': 'Consumer Cyclical',
                'country': 'Germany',
                'region': 'Europe',
                'revenue': 142000000000,
                'employees': 150000,
                'market_cap': 60000000000
            },
            {
                'symbol': 'AIR.PA',
                'name': 'Airbus SE',
                'industry': 'Aerospace & Defense',
                'sector': 'Industrials',
                'country': 'France',
                'region': 'Europe',
                'revenue': 60000000000,
                'employees': 130000,
                'market_cap': 110000000000
            },
            {
                'symbol': 'ITX.MC',
                'name': 'Industria de Diseño Textil, S.A.',
                'industry': 'Apparel Retail',
                'sector': 'Consumer Cyclical',
                'country': 'Spain',
                'region': 'Europe',
                'revenue': 32000000000,
                'employees': 165000,
                'market_cap': 100000000000
            },
            {
                'symbol': 'ENEL.MI',
                'name': 'Enel SpA',
                'industry': 'Utilities—Regulated Electric',
                'sector': 'Utilities',
                'country': 'Italy',
                'region': 'Europe',
                'revenue': 90000000000,
                'employees': 70000,
                'market_cap': 65000000000
            }
        ]
        
        return companies
    
    def _create_minimal_european_dataset(self):
        """Create a minimal dataset with European companies from different industries"""
        # This is a fallback method that creates a small but reliable dataset
        # with European companies across different industries
        companies = self._get_top_european_companies()
        
        # Add a few more companies from different countries and industries
        additional_companies = [
            {
                'symbol': 'BP.L',
                'name': 'BP p.l.c.',
                'industry': 'Oil & Gas Integrated',
                'sector': 'Energy',
                'country': 'United Kingdom',
                'region': 'Europe',
                'revenue': 240000000000,
                'employees': 65000,
                'market_cap': 95000000000
            },
            {
                'symbol': 'CS.PA',
                'name': 'AXA SA',
                'industry': 'Insurance—Diversified',
                'sector': 'Financial Services',
                'country': 'France',
                'region': 'Europe',
                'revenue': 100000000000,
                'employees': 150000,
                'market_cap': 70000000000
            },
            {
                'symbol': 'ROG.SW',
                'name': 'Roche Holding AG',
                'industry': 'Drug Manufacturers—General',
                'sector': 'Healthcare',
                'country': 'Switzerland',
                'region': 'Europe',
                'revenue': 65000000000,
                'employees': 100000,
                'market_cap': 250000000000
            }
        ]
        
        companies.extend(additional_companies)
        
        # Create DataFrame with consistent columns
        return pd.DataFrame(companies)
    
    def _get_tickers_for_sector(self, sector):
        """Get a list of ticker symbols for a specific sector"""
        try:
            # This is a simplified approach - in production you would use
            # a more robust API or subscription service for company data
            url = f"https://finance.yahoo.com/sector/{sector}"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            }
            
            response = requests.get(url, headers=headers)
            if response.status_code != 200:
                return []
                
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Extract ticker symbols from the page
            tickers = []
            for link in soup.find_all('a', href=re.compile(r'/quote/')):
                ticker = link.get('href').split('/quote/')[1].split('?')[0]
                if ticker and ticker not in tickers and '=' not in ticker:
                    tickers.append(ticker)
            
            return tickers
            
        except Exception as e:
            logger.error(f"Error getting tickers for sector {sector}: {str(e)}")
            return []
        
    def _get_related_industries(self, industry):
        """Get related industries based on improved industry mappings"""
        # Enhanced industry relationships mapping
        industry_map = {
            # Technology & Digital Media
            "Technology": ["Software", "Hardware", "Semiconductors", "Internet", "IT Services", 
                        "Digital Media", "Streaming", "E-Commerce", "FinTech", "Cloud Computing"],
            "Software": ["Technology", "Application Software", "Enterprise Software", "Internet Software", 
                        "SaaS", "Cloud Services", "Digital Media", "Internet"],
            "Digital Media": ["Technology", "Media", "Entertainment", "Streaming", "Software", "Internet"],
            "Streaming": ["Digital Media", "Entertainment", "Technology", "Media", "Internet"],
            "E-Commerce": ["Retail", "Technology", "Internet", "Consumer Goods", "Digital"],
            
            # Healthcare sector
            "Healthcare": ["Pharmaceuticals", "Medical Equipment", "Biotechnology", "Health Insurance", 
                        "Healthcare Services", "Life Sciences"],
            "Pharmaceuticals": ["Healthcare", "Biotechnology", "Life Sciences", "Drug Manufacturers", 
                            "Medical Research"],
            
            # Financial sector
            "Financial Services": ["Banking", "Insurance", "Asset Management", "Brokerages", "FinTech", 
                                "Credit Services", "Investment Services"],
            "Banking": ["Financial Services", "Diversified Banks", "Regional Banks", "Credit Services", 
                    "FinTech", "Investment Banking"],
            
            # Consumer & Retail
            "Retail": ["Consumer Goods", "Department Stores", "Specialty Retail", "E-Commerce", 
                    "Apparel", "Food & Beverage Retail"],
            "Consumer Goods": ["Retail", "Food & Beverage", "Household Products", "Apparel", 
                            "Consumer Electronics", "Luxury Goods"],
            
            # Industrial & Manufacturing
            "Manufacturing": ["Industrial Products", "Machinery", "Automotive", "Aerospace", 
                            "Electronics Manufacturing", "Industrial Equipment"],
            
            # Energy & Utilities
            "Energy": ["Oil & Gas", "Renewable Energy", "Utilities", "Pipeline", "Energy Services", 
                    "Green Energy"],
            
            # Telecommunications & Media
            "Telecommunications": ["Communication Services", "Wireless", "Cable", "Media", "Internet", 
                                "Networking Equipment"],
            "Media": ["Entertainment", "Digital Media", "Publishing", "Broadcasting", "Advertising", 
                    "Streaming", "Content Creation"],
            
            # Transportation
            "Automotive": ["Manufacturing", "Auto Parts", "Auto Manufacturers", "Transportation", "Electric Vehicles"],
            "Transportation": ["Logistics", "Airlines", "Shipping", "Rail", "Automotive", "Travel Services"],
            
            # Entertainment
            "Entertainment": ["Media", "Digital Media", "Streaming", "Gaming", "Music", "Film", "Sports"],
            "Music": ["Entertainment", "Digital Media", "Streaming", "Media"],
        }
        
        # Convert input to title case for consistent matching
        industry_title = industry.title()
        
        # Return related industries or just the original if not found
        related = industry_map.get(industry_title, [])
        
        # If no direct mapping, try partial matches
        if not related:
            for key, values in industry_map.items():
                if industry_title in key or key in industry_title:
                    related.extend(values)
                else:
                    # Check if industry matches any related industries
                    for value in values:
                        if industry_title in value or value in industry_title:
                            related.extend([key] + values)
                            break
        
        # Add the original industry if we found related ones
        if related and industry_title not in related:
            related.append(industry_title)
        
        # If still no matches, return the original
        return related if related else [industry_title]
    
    def _infer_sector_from_industry(self, industry):
        """Infer broader sector from specific industry"""
        industry_lower = industry.lower()
        
        # Map specific industries to broader sectors
        sector_mapping = {
            'technology': ['software', 'hardware', 'tech', 'digital', 'internet', 'computer', 'it', 
                        'cloud', 'saas', 'platform', 'streaming', 'semiconductor'],
            'healthcare': ['health', 'pharma', 'medical', 'biotech', 'life sciences', 'drug', 'care'],
            'financial': ['bank', 'financ', 'invest', 'insur', 'asset', 'capital', 'wealth', 'money'],
            'consumer': ['retail', 'consumer', 'food', 'beverage', 'apparel', 'goods', 'shop'],
            'industrial': ['manufact', 'industr', 'machinery', 'equipment', 'aerospace', 'defense'],
            'energy': ['energy', 'oil', 'gas', 'power', 'utility', 'electric', 'renewable'],
            'communications': ['telecom', 'media', 'communication', 'entertainment', 'broadcast', 'music'],
            'materials': ['material', 'chemical', 'mining', 'metal', 'paper', 'steel', 'timber'],
            'real estate': ['real estate', 'property', 'reit', 'construction', 'development']
        }
        
        for sector, keywords in sector_mapping.items():
            if any(keyword in industry_lower for keyword in keywords):
                return sector
                
        return "Other"
    
    def _filter_by_location(self, companies, region=None, country=None):
        """Filter companies by region or country"""
        filtered_companies = companies.copy()
        
        # Make sure the country column exists
        if 'country' not in filtered_companies.columns:
            logger.warning("Country column not found in data")
            filtered_companies['country'] = 'Unknown'
            
        # If we have no country or region to filter by, return all companies
        if not region and not country:
            return filtered_companies
        
        # If country is specified, filter by country first
        if country:
            country_matches = filtered_companies[
                filtered_companies['country'].str.contains(country, case=False, na=False)
            ]
            
            # If we have enough country matches, use those
            if len(country_matches) >= 5:
                return country_matches
            
            # Otherwise, keep the country matches and add regional matches
            country_filtered = True
        else:
            country_filtered = False
            country_matches = pd.DataFrame(columns=filtered_companies.columns)
        
        # If region is specified, filter by region
        if region:
            # Map of regions to their countries
            region_map = {
                "North America": ["USA", "United States", "Canada", "Mexico"],
                "Europe": ["UK", "United Kingdom", "Germany", "France", "Italy", "Spain", 
                        "Netherlands", "Switzerland", "Sweden", "Norway", "Finland", "Denmark",
                        "Belgium", "Austria", "Ireland", "Portugal", "Greece", "Poland", 
                        "Czech Republic", "Hungary", "Romania", "Slovakia", "Croatia", "Slovenia",
                        "Estonia", "Latvia", "Lithuania", "Luxembourg", "Iceland"],
                "Asia": ["China", "Japan", "South Korea", "India", "Taiwan", "Singapore", 
                        "Hong Kong", "Malaysia", "Indonesia", "Thailand"],
                "South America": ["Brazil", "Argentina", "Chile", "Colombia", "Peru"],
                "Oceania": ["Australia", "New Zealand"]
            }
            
            # Check if region is actually a country
            for region_name, countries_list in region_map.items():
                if region in countries_list:
                    # It's a country, filter directly
                    region_matches = filtered_companies[
                        filtered_companies['country'].str.contains(region, case=False, na=False)
                    ]
                    if country_filtered:
                        return pd.concat([country_matches, region_matches]).drop_duplicates()
                    else:
                        return region_matches
            
            # It's a region, get all countries in that region
            if region in region_map:
                countries_in_region = region_map[region]
                
                region_matches = pd.DataFrame()
                for country_name in countries_in_region:
                    matches = filtered_companies[
                        filtered_companies['country'].str.contains(country_name, case=False, na=False)
                    ]
                    region_matches = pd.concat([region_matches, matches])
                
                if country_filtered:
                    return pd.concat([country_matches, region_matches]).drop_duplicates()
                else:
                    return region_matches
                    
            # Check for region in the region column if available
            if 'region' in filtered_companies.columns:
                region_col_matches = filtered_companies[
                    filtered_companies['region'].str.contains(region, case=False, na=False)
                ]
                
                if len(region_col_matches) > 0:
                    if country_filtered:
                        return pd.concat([country_matches, region_col_matches]).drop_duplicates()
                    else:
                        return region_col_matches
        
        # If we got here and had filtered by country, return those matches
        if country_filtered and len(country_matches) > 0:
            return country_matches
        
        # If filtering resulted in empty dataset, return original
        if country_filtered or region:
            logger.warning(f"Location filtering (region={region}, country={country}) resulted in empty dataset. Returning all companies.")
        
        # Otherwise return all companies
        return filtered_companies
    
    def find_competitors(self, company_info, max_companies=10):
        """
        Find competitor companies based on industry, size, and region
        Returns a list of competitor companies with their information
        """
        # Make sure we have a company database
        if self.company_database is None:
            self.load_company_database()
        
        # Check if we have data in the database
        if len(self.company_database) == 0:
            logger.error("Company database is empty. Cannot find competitors.")
            return []
            
        logger.info(f"Finding competitors for: {company_info['name']}")
        
        # Step 1: Filter by industry using enhanced matching
        industry_matches = self._filter_by_industry(company_info['industry'])
        logger.info(f"Found {len(industry_matches)} companies in similar industries")
        
        # Step 2: Filter by region/country if available
        if company_info.get('region') or company_info.get('country'):
            region_matches = self._filter_by_location(
                industry_matches, 
                company_info.get('region'), 
                company_info.get('country')
            )
            logger.info(f"Found {len(region_matches)} companies in similar regions")
        else:
            region_matches = industry_matches
        
        # Step 3: Filter by size if available
        if company_info.get('revenue') or company_info.get('employees'):
            size_matches = self._filter_by_size(region_matches, company_info)
            logger.info(f"Found {len(size_matches)} companies of similar size")
        else:
            size_matches = region_matches
        
        # Step 4: Rank by similarity and return top matches
        competitors = self._rank_companies(size_matches, company_info)
        
        # Limit to the specified number of companies
        top_competitors = competitors[:max_companies]
        logger.info(f"Selected top {len(top_competitors)} most similar companies")
        
        # Check if we filtered too aggressively and have no matches
        if len(top_competitors) == 0 and len(self.company_database) > 0:
            logger.warning("No matches found with current filters. Returning industry matches only.")
            # Return industry matches without region/size filtering
            industry_competitors = self._rank_companies(industry_matches, company_info)
            top_competitors = industry_competitors[:max_companies]
            logger.info(f"Selected top {len(top_competitors)} industry-matched companies")
        
        return top_competitors
    
    def _filter_by_size(self, companies, company_info):
        """Filter companies by size (revenue and/or employee count)"""
        filtered_companies = companies.copy()
        
        # Check for required columns
        size_columns = ['revenue', 'employees']
        for col in size_columns:
            if col not in filtered_companies.columns:
                logger.warning(f"Column '{col}' not found in company database. Adding placeholder values.")
                filtered_companies[col] = None
        
        # Filter by revenue if available
        if company_info.get('revenue') and filtered_companies['revenue'].notna().sum() > 0:
            revenue = company_info['revenue']
            # Companies within 25% to 400% of target revenue (wider range)
            min_revenue = revenue * 0.25
            max_revenue = revenue * 4.0
            
            # Exclude NaN values from revenue filter
            revenue_filter = (
                (filtered_companies['revenue'].notna()) &
                (filtered_companies['revenue'] >= min_revenue) & 
                (filtered_companies['revenue'] <= max_revenue)
            )
            revenue_filtered = filtered_companies[revenue_filter]
            
            # If we have enough companies after revenue filtering, use those
            if len(revenue_filtered) >= 5:
                filtered_companies = revenue_filtered
        
        # Filter by employee count if available
        if company_info.get('employees') and filtered_companies['employees'].notna().sum() > 0:
            employees = company_info['employees']
            # Companies within 25% to 400% of employee count (wider range)
            min_employees = employees * 0.25
            max_employees = employees * 4.0
            
            # Exclude NaN values from employee filter
            employee_filter = (
                (filtered_companies['employees'].notna()) &
                (filtered_companies['employees'] >= min_employees) & 
                (filtered_companies['employees'] <= max_employees)
            )
            employee_filtered = filtered_companies[employee_filter]
            
            # If we have enough companies after employee filtering, use those
            if len(employee_filtered) >= 5:
                filtered_companies = employee_filtered
        
        # If we filtered too aggressively, relax constraints
        if len(filtered_companies) < 5 and len(companies) > 5:
            logger.info("Relaxing size constraints to find more matches")
            
            # Try wider revenue range
            if company_info.get('revenue') and 'revenue' in companies.columns and companies['revenue'].notna().sum() > 0:
                revenue = company_info['revenue']
                min_revenue = revenue * 0.1  # 10% of target
                max_revenue = revenue * 10.0   # 1000% of target
                
                revenue_filter = (
                    (companies['revenue'].notna()) &
                    (companies['revenue'] >= min_revenue) & 
                    (companies['revenue'] <= max_revenue)
                )
                revenue_filtered = companies[revenue_filter]
                
                if len(revenue_filtered) >= 5:
                    return revenue_filtered
            
            # If still not enough, return original companies
            return companies
        
        return filtered_companies
    
    def _filter_by_industry(self, industry):
        """Enhanced filter for companies by industry and sector"""
        if not industry:
            return self.company_database
        
        # Normalize the industry name
        industry_lower = industry.lower()
        
        # Make sure required columns exist before filtering
        required_columns = ['industry', 'sector']
        for col in required_columns:
            if col not in self.company_database.columns:
                logger.warning(f"Column '{col}' not found in company database")
                # Add the column with default values
                self.company_database[col] = "Unknown"
        
        # 1. First try exact matching (most precise)
        exact_matches = self.company_database[
            (self.company_database['industry'].str.lower() == industry_lower) |
            (self.company_database['sector'].str.lower() == industry_lower)
        ]
        
        # 2. If we don't have enough exact matches, try partial matching
        if len(exact_matches) < 10:
            # First try contains with the full industry name
            partial_matches = self.company_database[
                (self.company_database['industry'].str.contains(industry_lower, case=False, na=False)) |
                (self.company_database['sector'].str.contains(industry_lower, case=False, na=False))
            ]
            
            # Then try keywords within the industry name
            if len(partial_matches) < 10:
                # Split industry into keywords
                keywords = [word for word in industry_lower.split() if len(word) > 3 and word not in stopwords.words('english')]
                
                keyword_matches = pd.DataFrame()
                for keyword in keywords:
                    matches = self.company_database[
                        (self.company_database['industry'].str.contains(keyword, case=False, na=False)) |
                        (self.company_database['sector'].str.contains(keyword, case=False, na=False))
                    ]
                    keyword_matches = pd.concat([keyword_matches, matches])
                
                # Combine all partial matches
                partial_matches = pd.concat([partial_matches, keyword_matches])
            
            combined_matches = pd.concat([exact_matches, partial_matches]).drop_duplicates()
        else:
            combined_matches = exact_matches
        
        # 3. If we still don't have enough matches, try related industries
        if len(combined_matches) < 10:
            related_industries = self._get_related_industries(industry)
            
            related_matches = pd.DataFrame()
            for related in related_industries:
                # Try exact match on related industries
                exact_related = self.company_database[
                    (self.company_database['industry'].str.lower() == related.lower()) |
                    (self.company_database['sector'].str.lower() == related.lower())
                ]
                
                # Try partial match on related industries
                partial_related = self.company_database[
                    (self.company_database['industry'].str.contains(related, case=False, na=False)) |
                    (self.company_database['sector'].str.contains(related, case=False, na=False))
                ]
                
                related_matches = pd.concat([related_matches, exact_related, partial_related])
            
            combined_matches = pd.concat([combined_matches, related_matches]).drop_duplicates()
        
        # 4. Add fallback if we still don't have matches
        if len(combined_matches) < 5:
            # Get sector from industry
            possible_sector = self._infer_sector_from_industry(industry)
            
            sector_matches = self.company_database[
                self.company_database['sector'].str.contains(possible_sector, case=False, na=False)
            ]
            
            combined_matches = pd.concat([combined_matches, sector_matches]).drop_duplicates()
        
        # 5. Final fallback - if still no matches, return a subset of all companies
        if len(combined_matches) == 0:
            logger.warning(f"No matches found for industry '{industry}'. Returning random sample.")
            return self.company_database.sample(min(10, len(self.company_database)))
            
        # Return the combined matches
        return combined_matches
    
    def find_similar_companies(pdf_path, max_companies=10, rebuild_database=False):
        """
        Main function to find similar companies based on a financial PDF
        
        Args:
            pdf_path: Path to the processed financial PDF JSON data
            max_companies: Maximum number of similar companies to return
            rebuild_database: Whether to rebuild the company database, even if it exists
            
        Returns:
            List of similar companies with their information
        """
        logger.info(f"Starting competitor discovery process for: {pdf_path}")
        
        # Extract company name from PDF filename for fallback
        filename = os.path.basename(pdf_path)
        company_name = re.sub(r'[_\.]', ' ', os.path.splitext(filename)[0])
        
        # Initialize CompetitorFinder
        finder = CompetitorFinder()
        
        # Check if database exists and prompt user if they want to rebuild
        cache_file = os.path.join(finder.cache_dir, "company_database.csv")
        if os.path.exists(cache_file) and not rebuild_database:
            user_input = input("Company database already exists. Would you like to rebuild it with the latest data? (y/n): ")
            rebuild_database = user_input.lower() in ('y', 'yes')
        
        # Load or rebuild database based on user choice
        finder.load_company_database(rebuild=rebuild_database)
        
        # Extract company information from the processed PDF data
        company_info = finder.extract_company_info(pdf_path, company_name)
        
        # Log the extracted company information
        logger.info("Extracted company information:")
        for key, value in company_info.items():
            if value:
                logger.info(f"  - {key}: {value}")
        
        # Find similar companies
        similar_companies = finder.find_competitors(company_info, max_companies)
        
        logger.info(f"Found {len(similar_companies)} similar companies")
        
        return similar_companies
    
    def _calculate_industry_similarity(self, industry_x, industry_y):
        """Calculate similarity between two industry strings"""
        if not industry_x or not industry_y:
            return 0.0
            
        # Handle non-string types
        industry_x = str(industry_x)
        industry_y = str(industry_y)
            
        industry_x_lower = industry_x.lower()
        industry_y_lower = industry_y.lower()
        
        # Exact match
        if industry_x_lower == industry_y_lower:
            return 1.0
            
        # One contains the other completely
        if industry_x_lower in industry_y_lower or industry_y_lower in industry_x_lower:
            return 0.8
        
        # Split into words and remove stopwords
        x_words = set([w for w in industry_x_lower.split() if w not in stopwords.words('english')])
        y_words = set([w for w in industry_y_lower.split() if w not in stopwords.words('english')])
        
        # Calculate word overlap
        if not x_words or not y_words:
            return 0.0
            
        # Jaccard similarity
        intersection = len(x_words.intersection(y_words))
        union = len(x_words.union(y_words))
        
        return intersection / union if union > 0 else 0.0
    
    def _rank_companies(self, companies, company_info):
        """Improved ranking of companies by similarity to the target company"""
        if len(companies) == 0:
            return []
        
        # Create a copy to avoid modifying the original
        ranked_companies = companies.copy()
        
        # Make sure required columns exist with default values
        required_columns = ['industry', 'sector', 'country', 'revenue', 'employees']
        for col in required_columns:
            if col not in ranked_companies.columns:
                ranked_companies[col] = None
        
        # Calculate similarity scores
        ranked_companies['similarity_score'] = 0
        
        # Industry similarity (highest weight - increased from 5 to 8)
        if company_info.get('industry'):
            # More nuanced matching with keyword analysis
            ranked_companies['industry_match'] = ranked_companies['industry'].apply(
                lambda x: self._calculate_industry_similarity(x, company_info['industry'])
            )
            ranked_companies['similarity_score'] += ranked_companies['industry_match'] * 8
        
        # Sector similarity
        if company_info.get('industry'):
            # Infer sector from the target industry
            target_sector = self._infer_sector_from_industry(company_info['industry'])
            ranked_companies['sector_match'] = ranked_companies['sector'].apply(
                lambda x: 1.0 if x and str(x).lower() == target_sector.lower() else
                        0.7 if x and target_sector.lower() in str(x).lower() else
                        0.3 if x and any(sector in str(x).lower() for sector in 
                                self._get_related_industries(target_sector)) else
                        0.0
            )
            ranked_companies['similarity_score'] += ranked_companies['sector_match'] * 4
        
        # Region/country similarity
        if company_info.get('country'):
            ranked_companies['country_match'] = ranked_companies['country'].apply(
                lambda x: 1.0 if x and str(x).lower() == str(company_info['country']).lower() else 0.0
            )
            ranked_companies['similarity_score'] += ranked_companies['country_match'] * 3
        
        # Revenue similarity
        if company_info.get('revenue'):
            # Calculate percentage difference in revenue
            ranked_companies['revenue_diff'] = ranked_companies['revenue'].apply(
                lambda x: abs(float(x or 0) - float(company_info['revenue'])) / float(company_info['revenue']) 
                if x is not None and pd.notna(x) and company_info['revenue'] else 1.0
            )
            
            # Convert to similarity score (1.0 = perfect match, 0.0 = very different)
            ranked_companies['revenue_score'] = 1.0 - ranked_companies['revenue_diff'].clip(0, 1)
            ranked_companies['similarity_score'] += ranked_companies['revenue_score'] * 2
        
        # Employee count similarity
        if company_info.get('employees'):
            # Calculate percentage difference in employee count
            ranked_companies['employee_diff'] = ranked_companies['employees'].apply(
                lambda x: abs(float(x or 0) - float(company_info['employees'])) / float(company_info['employees'])
                if x is not None and pd.notna(x) and company_info['employees'] else 1.0
            )
            
            # Convert to similarity score
            ranked_companies['employee_score'] = 1.0 - ranked_companies['employee_diff'].clip(0, 1)
            ranked_companies['similarity_score'] += ranked_companies['employee_score'] * 1
        
        # Sort by similarity score (highest first)
        ranked_companies = ranked_companies.sort_values('similarity_score', ascending=False)
        
        # Convert to list of dictionaries for easier processing
        result = []
        for _, row in ranked_companies.iterrows():
            company_dict = row.to_dict()
            # Clean up any NaN values
            for key, value in company_dict.items():
                if pd.isna(value):
                    company_dict[key] = None
            result.append(company_dict)
        
        return result

# When run directly, test with a European company example
if __name__ == "__main__":
    # Example European company
    test_company = {
        "name": "SAP",
        "industry": "Software",
        "sector": "Technology",
        "country": "Germany",
        "revenue": 30000000000,  # €30 billion
        "employees": 107000
    }
    
    finder = CompetitorFinder()
    
    # Check if database exists and prompt user
    cache_file = os.path.join(finder.cache_dir, "company_database.csv")
    rebuild = False
    if os.path.exists(cache_file):
        user_input = input("Company database already exists. Would you like to rebuild it with the latest data? (y/n): ")
        rebuild = user_input.lower() in ('y', 'yes')
    
    # Load or rebuild database
    finder.load_company_database(rebuild=rebuild)
    
    # Find competitors
    competitors = finder.find_competitors(test_company)
    
    print("\nTop European competitors found for SAP:")
    for i, company in enumerate(competitors[:5], 1):
        print(f"\n{i}. {company['name']} ({company.get('symbol', 'N/A')})")
        print(f"   Industry: {company.get('industry', 'N/A')}")
        print(f"   Region: {company.get('region', 'N/A')}, Country: {company.get('country', 'N/A')}")
        print(f"   Similarity score: {company.get('similarity_score', 'N/A')}")
        print(f"   Revenue: {company.get('revenue', 'N/A')}")
        print(f"   Employees: {company.get('employees', 'N/A')}")