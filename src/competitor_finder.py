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
            "Technology": ["tech", "software", "digital", "cyber", "systems", "IT"],
            "Financial Services": ["bank", "finance", "invest", "capital", "financial", "asset"],
            "Energy": ["energy", "oil", "gas", "solar", "power", "renewable"],
            "Manufacturing": ["manufacturing", "industrial", "factory", "product", "fabrication"],
            "Retail": ["retail", "store", "shop", "mart", "market", "consumer"],
            "Telecommunications": ["telecom", "communication", "network", "mobile", "wireless"],
            "Real Estate": ["property", "real estate", "realty", "construction", "building"],
            "Transportation": ["transport", "logistics", "shipping", "delivery", "freight"],
            "Media": ["media", "entertainment", "film", "game", "broadcast", "production"]
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
    
    def load_company_database(self):
        """Load the company database from cache or external sources"""
        cache_file = os.path.join(self.cache_dir, "company_database.csv")
        
        # Try to load from cache first
        if os.path.exists(cache_file):
            logger.info("Loading company database from cache...")
            self.company_database = pd.read_csv(cache_file)
            logger.info(f"Loaded {len(self.company_database)} companies from cache")
            return self.company_database
        
        # If not in cache, create from multiple sources
        logger.info("Building company database from external sources...")
        
        # Initialize an empty database
        self.company_database = pd.DataFrame()
        
        # Try loading from Yahoo Finance
        try:
            logger.info("Fetching data from Yahoo Finance sectors...")
            sectors = [
                'technology', 'financial', 'healthcare', 'consumer_cyclical',
                'industrials', 'consumer_defensive', 'energy', 'utilities',
                'communication_services', 'real_estate', 'basic_materials'
            ]
            
            all_companies = []
            
            for sector in sectors:
                # Get tickers for this sector
                tickers = self._get_tickers_for_sector(sector)
                
                for symbol in tickers[:50]:  # Limit to 50 companies per sector
                    try:
                        # Get company info from Yahoo Finance
                        ticker = yf.Ticker(symbol)
                        info = ticker.info
                        
                        company = {
                            'symbol': symbol,
                            'name': info.get('shortName', info.get('longName', symbol)),
                            'industry': info.get('industry', 'Unknown'),
                            'sector': info.get('sector', 'Unknown'),
                            'country': info.get('country', 'Unknown'),
                            'revenue': info.get('totalRevenue', None),
                            'employees': info.get('fullTimeEmployees', None),
                            'market_cap': info.get('marketCap', None)
                        }
                        
                        all_companies.append(company)
                        logger.info(f"Added {company['name']} ({symbol}) - {company['industry']}")
                        
                        # Add a short delay to avoid rate limiting
                        time.sleep(0.2)
                        
                    except Exception as e:
                        logger.warning(f"Error fetching data for {symbol}: {str(e)}")
                
                logger.info(f"Processed {len(tickers)} companies in {sector} sector")
            
            # Convert to DataFrame
            if all_companies:
                self.company_database = pd.DataFrame(all_companies)
                
                # Save to cache
                self.company_database.to_csv(cache_file, index=False)
                logger.info(f"Saved {len(self.company_database)} companies to cache")
                
                return self.company_database
                
        except Exception as e:
            logger.error(f"Error building company database: {str(e)}")
        
        # If all else fails, create a sample database
        logger.warning("Using sample company database as fallback")
        self.company_database = self._create_sample_database()
        self.company_database.to_csv(cache_file, index=False)
        
        return self.company_database
    
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
    
    def _create_sample_database(self):
        """Create a sample company database for testing"""
        # Create sample data with common industries
        industries = [
            "Healthcare", "Pharmaceuticals", "Technology", "Software", 
            "Financial Services", "Banking", "Manufacturing", "Retail",
            "Energy", "Consumer Goods", "Telecommunications", "Automotive"
        ]
        
        sectors = [
            "Healthcare", "Technology", "Financial Services", "Industrials",
            "Consumer Discretionary", "Energy", "Communication Services",
            "Consumer Staples", "Materials", "Utilities", "Real Estate"
        ]
        
        regions = ["North America", "Europe", "Asia", "South America"]
        countries = {
            "North America": ["USA", "Canada", "Mexico"],
            "Europe": ["UK", "Germany", "France", "Finland", "Sweden", "Italy", "Spain"],
            "Asia": ["Japan", "China", "India", "South Korea"],
            "South America": ["Brazil", "Argentina", "Chile"]
        }
        
        # Generate ticker symbols
        all_tickers = []
        for i in range(1000):
            ticker = ''.join([chr(65 + (ord(c) + i) % 26) for c in 'AAPL'[:2+i%2]])
            all_tickers.append(ticker)
        
        # Create 1000 sample companies
        companies = []
        for i in range(1000):
            region = regions[i % len(regions)]
            country = countries[region][i % len(countries[region])]
            industry = industries[i % len(industries)]
            sector = sectors[i % len(sectors)]
            
            company = {
                'symbol': all_tickers[i],
                'name': f"Company {i}",
                'industry': industry,
                'sector': sector,
                'country': country,
                'region': region,
                'revenue': (i % 10 + 1) * 100000000,  # Revenue between $100M and $1B
                'employees': (i % 20 + 1) * 1000,     # 1,000 to 20,000 employees
                'market_cap': (i % 15 + 1) * 500000000  # Market cap between $500M and $7.5B
            }
            companies.append(company)
        
        return pd.DataFrame(companies)
    
    def find_competitors(self, company_info, max_companies=10):
        """
        Find competitor companies based on industry, size, and region
        Returns a list of competitor companies with their information
        """
        # Make sure we have a company database
        if self.company_database is None:
            self.load_company_database()
        
        logger.info(f"Finding competitors for: {company_info['name']}")
        
        # Step 1: Filter by industry
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
        
        return top_competitors
    
    def _filter_by_industry(self, industry):
        """Filter companies by industry and sector"""
        if not industry:
            return self.company_database
        
        # First try exact matching
        exact_matches = self.company_database[
            (self.company_database['industry'].str.lower() == industry.lower()) |
            (self.company_database['sector'].str.lower() == industry.lower())
        ]
        
        # If we don't have enough exact matches, try partial matching
        if len(exact_matches) < 10:
            partial_matches = self.company_database[
                (self.company_database['industry'].str.contains(industry, case=False, na=False)) |
                (self.company_database['sector'].str.contains(industry, case=False, na=False))
            ]
            combined_matches = pd.concat([exact_matches, partial_matches]).drop_duplicates()
        else:
            combined_matches = exact_matches
        
        # If we still don't have enough matches, try related industries
        if len(combined_matches) < 10:
            related_industries = self._get_related_industries(industry)
            
            related_matches = pd.DataFrame()
            for related in related_industries:
                matches = self.company_database[
                    (self.company_database['industry'].str.contains(related, case=False, na=False)) |
                    (self.company_database['sector'].str.contains(related, case=False, na=False))
                ]
                related_matches = pd.concat([related_matches, matches])
            
            combined_matches = pd.concat([combined_matches, related_matches]).drop_duplicates()
        
        return combined_matches
    
    def _get_related_industries(self, industry):
        """Get related industries based on industry mappings"""
        # Industry relationships mapping
        industry_map = {
            "Healthcare": ["Pharmaceuticals", "Medical Equipment", "Biotechnology", "Health Insurance"],
            "Pharmaceuticals": ["Healthcare", "Biotechnology", "Life Sciences", "Drug Manufacturers"],
            "Technology": ["Software", "Hardware", "Semiconductors", "Internet", "IT Services"],
            "Software": ["Technology", "Application Software", "Enterprise Software", "Internet Software"],
            "Financial Services": ["Banking", "Insurance", "Asset Management", "Brokerages"],
            "Banking": ["Financial Services", "Diversified Banks", "Regional Banks", "Credit Services"],
            "Manufacturing": ["Industrial Products", "Machinery", "Automotive", "Aerospace"],
            "Retail": ["Consumer Goods", "Department Stores", "Specialty Retail", "E-Commerce"],
            "Energy": ["Oil & Gas", "Renewable Energy", "Utilities", "Pipeline"],
            "Consumer Goods": ["Retail", "Food & Beverage", "Household Products", "Apparel"],
            "Telecommunications": ["Communication Services", "Wireless", "Cable", "Media"],
            "Automotive": ["Manufacturing", "Auto Parts", "Auto Manufacturers", "Transportation"]
        }
        
        # Convert input to title case for consistent matching
        industry_title = industry.title()
        
        # Return related industries or just the original if not found
        related = industry_map.get(industry_title, [industry_title])
        return related
    
    def _filter_by_location(self, companies, region=None, country=None):
        """Filter companies by region or country"""
        filtered_companies = companies.copy()
        
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
        
        # If region is specified, filter by region
        if region:
            # Map of regions to their countries
            region_map = {
                "North America": ["USA", "United States", "Canada", "Mexico"],
                "Europe": ["UK", "United Kingdom", "Germany", "France", "Italy", "Spain", 
                          "Netherlands", "Switzerland", "Sweden", "Norway", "Finland", "Denmark"],
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
        
        # If we got here and had filtered by country, return those matches
        if country_filtered:
            return country_matches
        
        # Otherwise return all companies
        return filtered_companies
    
    def _filter_by_size(self, companies, company_info):
        """Filter companies by size (revenue and/or employee count)"""
        filtered_companies = companies.copy()
        
        # Filter by revenue if available
        if company_info.get('revenue') and 'revenue' in filtered_companies.columns:
            revenue = company_info['revenue']
            # Companies within 50% to 200% of target revenue
            min_revenue = revenue * 0.5
            max_revenue = revenue * 2.0
            
            revenue_filter = (
                (filtered_companies['revenue'] >= min_revenue) & 
                (filtered_companies['revenue'] <= max_revenue)
            )
            revenue_filtered = filtered_companies[revenue_filter]
            
            # If we have enough companies after revenue filtering, use those
            if len(revenue_filtered) >= 5:
                filtered_companies = revenue_filtered
        
        # Filter by employee count if available
        if company_info.get('employees') and 'employees' in filtered_companies.columns:
            employees = company_info['employees']
            # Companies within 50% to 200% of employee count
            min_employees = employees * 0.5
            max_employees = employees * 2.0
            
            employee_filter = (
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
            if company_info.get('revenue') and 'revenue' in companies.columns:
                revenue = company_info['revenue']
                min_revenue = revenue * 0.25  # 25% of target
                max_revenue = revenue * 4.0   # 400% of target
                
                revenue_filter = (
                    (companies['revenue'] >= min_revenue) & 
                    (companies['revenue'] <= max_revenue)
                )
                revenue_filtered = companies[revenue_filter]
                
                if len(revenue_filtered) >= 5:
                    return revenue_filtered
            
            # If still not enough, return original companies
            return companies
        
        return filtered_companies
    
    def _rank_companies(self, companies, company_info):
        """Rank companies by similarity to the target company"""
        if len(companies) == 0:
            return []
        
        # Create a copy to avoid modifying the original
        ranked_companies = companies.copy()
        
        # Calculate similarity scores
        ranked_companies['similarity_score'] = 0
        
        # Industry similarity (highest weight)
        if company_info.get('industry'):
            ranked_companies['industry_match'] = ranked_companies['industry'].apply(
                lambda x: 1.0 if x and x.lower() == company_info['industry'].lower() else 
                           0.5 if x and company_info['industry'].lower() in x.lower() else 
                           0.0
            )
            ranked_companies['similarity_score'] += ranked_companies['industry_match'] * 5
        
        # Sector similarity
        if company_info.get('industry') and 'sector' in ranked_companies.columns:
            ranked_companies['sector_match'] = ranked_companies['sector'].apply(
                lambda x: 1.0 if x and x.lower() == company_info['industry'].lower() else
                           0.5 if x and company_info['industry'].lower() in x.lower() else
                           0.0
            )
            ranked_companies['similarity_score'] += ranked_companies['sector_match'] * 3
        
        # Region/country similarity
        if company_info.get('country') and 'country' in ranked_companies.columns:
            ranked_companies['country_match'] = ranked_companies['country'].apply(
                lambda x: 1.0 if x and x.lower() == company_info['country'].lower() else 0.0
            )
            ranked_companies['similarity_score'] += ranked_companies['country_match'] * 3
        
        # Revenue similarity
        if company_info.get('revenue') and 'revenue' in ranked_companies.columns:
            # Calculate percentage difference in revenue
            ranked_companies['revenue_diff'] = ranked_companies['revenue'].apply(
                lambda x: abs((x or 0) - company_info['revenue']) / company_info['revenue'] 
                if x and company_info['revenue'] else 1.0
            )
            
            # Convert to similarity score (1.0 = perfect match, 0.0 = very different)
            ranked_companies['revenue_score'] = 1.0 - ranked_companies['revenue_diff'].clip(0, 1)
            ranked_companies['similarity_score'] += ranked_companies['revenue_score'] * 2
        
        # Employee count similarity
        if company_info.get('employees') and 'employees' in ranked_companies.columns:
            # Calculate percentage difference in employee count
            ranked_companies['employee_diff'] = ranked_companies['employees'].apply(
                lambda x: abs((x or 0) - company_info['employees']) / company_info['employees']
                if x and company_info['employees'] else 1.0
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

def find_similar_companies(pdf_path, max_companies=10):
    """
    Main function to find similar companies based on a financial PDF
    
    Args:
        pdf_path: Path to the processed financial PDF JSON data
        max_companies: Maximum number of similar companies to return
        
    Returns:
        List of similar companies with their information
    """
    logger.info(f"Starting competitor discovery process for: {pdf_path}")
    
    # Extract company name from PDF filename for fallback
    filename = os.path.basename(pdf_path)
    company_name = re.sub(r'[_\.]', ' ', os.path.splitext(filename)[0])
    
    # Initialize CompetitorFinder
    finder = CompetitorFinder()
    
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

# When run directly, test with a sample company
if __name__ == "__main__":
    # Sample usage
    sample_company = {
        "name": "AstraZeneca",
        "industry": "Pharmaceuticals",
        "country": "UK",
        "revenue": 45000000000,  # $45 billion
        "employees": 83000
    }
    
    finder = CompetitorFinder()
    competitors = finder.find_competitors(sample_company)
    
    print("\nTop competitors found:")
    for i, company in enumerate(competitors[:5], 1):
        print(f"\n{i}. {company['name']} ({company.get('symbol', 'N/A')})")
        print(f"   Industry: {company.get('industry', 'N/A')}")
        print(f"   Region: {company.get('region', 'N/A')}, Country: {company.get('country', 'N/A')}")
        print(f"   Similarity score: {company.get('similarity_score', 'N/A')}")