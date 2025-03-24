#!/usr/bin/env python
"""
Competitor Matcher for Financial Analysis
-----------------------------------------
This script finds similar competitor companies by matching industry, size, and financials.
"""

import os
import pandas as pd
import numpy as np
import logging
from sklearn.preprocessing import MinMaxScaler
from sklearn.metrics.pairwise import cosine_similarity

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('CompetitorMatcher')

class CompetitorMatcher:
    def __init__(self, company_database_path):
        """Initialize with pre-built company database."""
        try:
            self.companies_df = pd.read_csv(company_database_path)
            logger.info(f"Loaded company database with {len(self.companies_df)} companies")
            
            # Fill missing values with appropriate strategies
            self._preprocess_data()
            
        except Exception as e:
            logger.error(f"Error loading company database: {str(e)}")
            self.companies_df = pd.DataFrame()
    
    def _preprocess_data(self):
        """Preprocess the database for matching."""
        # Handle missing values
        if 'revenue' in self.companies_df.columns:
            self.companies_df['revenue'] = self.companies_df['revenue'].fillna(self.companies_df['revenue'].median())
        
        if 'employees' in self.companies_df.columns:
            self.companies_df['employees'] = self.companies_df['employees'].fillna(self.companies_df['employees'].median())
        
        if 'market_cap' in self.companies_df.columns:
            self.companies_df['market_cap'] = self.companies_df['market_cap'].fillna(self.companies_df['market_cap'].median())
        
        if 'profit_margin' in self.companies_df.columns:
            self.companies_df['profit_margin'] = self.companies_df['profit_margin'].fillna(self.companies_df['profit_margin'].median())
        
        # Ensure all companies have an industry and sector
        if 'industry' in self.companies_df.columns and 'sector' in self.companies_df.columns:
            # Fill missing industry with sector
            industry_missing = self.companies_df['industry'].isna() & ~self.companies_df['sector'].isna()
            self.companies_df.loc[industry_missing, 'industry'] = self.companies_df.loc[industry_missing, 'sector']
            
            # Fill missing sector with industry
            sector_missing = self.companies_df['sector'].isna() & ~self.companies_df['industry'].isna()
            self.companies_df.loc[sector_missing, 'sector'] = self.companies_df.loc[sector_missing, 'industry']
            
            # Fill any remaining with "Unknown"
            self.companies_df['industry'] = self.companies_df['industry'].fillna("Unknown")
            self.companies_df['sector'] = self.companies_df['sector'].fillna("Unknown")
    
    def _map_industry(self, input_industry):
        """Map input industry text to database industries."""
        input_lower = input_industry.lower()
        
        # First try exact match (case insensitive)
        exact_matches = self.companies_df[self.companies_df['industry'].str.lower() == input_lower]
        if not exact_matches.empty:
            return exact_matches.iloc[0]['industry']
        
        # Try matching keywords
        industry_keywords = {
            'software': ['software', 'saas', 'cloud', 'application'],
            'hardware': ['hardware', 'computer', 'device', 'electronics'],
            'banking': ['bank', 'financial', 'credit', 'loan'],
            'retail': ['retail', 'shop', 'store', 'ecommerce'],
            'manufacturing': ['manufacturing', 'factory', 'production'],
            'healthcare': ['health', 'medical', 'hospital', 'pharma'],
            'energy': ['energy', 'oil', 'gas', 'power', 'utility'],
            'telecom': ['telecom', 'communications', 'network', 'phone'],
            'media': ['media', 'entertainment', 'publishing', 'news'],
            'food': ['food', 'beverage', 'restaurant', 'grocery'],
            'transportation': ['transport', 'logistics', 'shipping']
        }
        
        for industry, keywords in industry_keywords.items():
            if any(keyword in input_lower for keyword in keywords):
                # Find a matching industry in our database
                industry_matches = self.companies_df[
                    self.companies_df['industry'].str.lower().str.contains(industry)
                ]
                if not industry_matches.empty:
                    return industry_matches.iloc[0]['industry']
        
        # If no match found, return the input as is
        return input_industry
    
    def find_competitors(self, input_company, top_n=10, include_financials=True):
        """
        Find the most similar companies to the input company.
        
        Parameters:
        input_company: dict with company details (industry, revenue, employees, etc.)
        top_n: number of top competitors to return
        include_financials: whether to include financial metrics in matching
        
        Returns:
        DataFrame with top_n most similar companies
        """
        if self.companies_df.empty:
            logger.error("Company database is empty")
            return pd.DataFrame()
        
        logger.info(f"Finding competitors for {input_company.get('company_name', 'unnamed company')}")
        
        # Map input industry to database nomenclature
        if 'industry' in input_company:
            input_company['mapped_industry'] = self._map_industry(input_company['industry'])
        
        # First-pass filter: Industry or sector match
        matched_companies = pd.DataFrame()
        
        if 'mapped_industry' in input_company and 'industry' in self.companies_df.columns:
            # Try industry match first
            industry_filter = self.companies_df['industry'].str.lower() == input_company['mapped_industry'].lower()
            industry_matches = self.companies_df[industry_filter].copy()
            
            if len(industry_matches) >= 5:
                matched_companies = industry_matches
                logger.info(f"Found {len(matched_companies)} companies in the same industry")
            else:
                # Try broader sector match
                if 'sector' in self.companies_df.columns:
                    # Find sector based on mapped industry
                    possible_sectors = self.companies_df[self.companies_df['industry'].str.lower() == 
                                                    input_company['mapped_industry'].lower()]['sector'].unique()
                    
                    if len(possible_sectors) > 0:
                        sector = possible_sectors[0]
                        sector_filter = self.companies_df['sector'] == sector
                        matched_companies = self.companies_df[sector_filter].copy()
                        logger.info(f"Found {len(matched_companies)} companies in the same sector")
        
        # If we still don't have enough matches, just use all companies
        if len(matched_companies) < 5:
            logger.warning("Few industry/sector matches, using all companies")
            matched_companies = self.companies_df.copy()
        
        # Second-pass filter: Size similarity (revenue range and/or employee count)
        size_filtered = pd.DataFrame()
        
        if include_financials and 'revenue' in input_company and 'revenue' in matched_companies.columns:
            input_revenue = float(input_company['revenue'])
            
            # Define a revenue range (e.g., 0.2x to 5x the input company)
            min_revenue = input_revenue * 0.2
            max_revenue = input_revenue * 5
            
            # Apply revenue filter
            size_filter = (matched_companies['revenue'] >= min_revenue) & (matched_companies['revenue'] <= max_revenue)
            size_filtered = matched_companies[size_filter].copy()
            
            logger.info(f"Found {len(size_filtered)} companies in the similar revenue range")
            
            # If too few companies, try employee count
            if len(size_filtered) < 5 and 'employees' in input_company and 'employees' in matched_companies.columns:
                input_employees = float(input_company['employees'])
                min_employees = input_employees * 0.2
                max_employees = input_employees * 5
                
                employee_filter = (matched_companies['employees'] >= min_employees) & (matched_companies['employees'] <= max_employees)
                size_filtered = matched_companies[employee_filter].copy()
                
                logger.info(f"Found {len(size_filtered)} companies with similar employee count")
        
        # If size filtering resulted in too few companies, go back to industry matches
        if len(size_filtered) < 5:
            logger.warning("Few size matches, reverting to industry/sector matches")
            size_filtered = matched_companies.copy()
        
        # If we have financial metrics, calculate similarity scores
        if include_financials:
            # Prepare features for similarity calculation
            numeric_features = []
            
            if 'revenue' in size_filtered.columns and 'revenue' in input_company:
                numeric_features.append('revenue')
                
            if 'employees' in size_filtered.columns and 'employees' in input_company:
                numeric_features.append('employees')
                
            if 'profit_margin' in size_filtered.columns and 'profit_margin' in input_company:
                numeric_features.append('profit_margin')
                
            if 'market_cap' in size_filtered.columns and 'market_cap' in input_company:
                numeric_features.append('market_cap')
            
            if numeric_features:
                # Create scaler
                scaler = MinMaxScaler()
                
                # Scale company features
                company_features = size_filtered[numeric_features].values
                company_features_scaled = scaler.fit_transform(company_features)
                
                # Create input features array
                input_features = np.zeros((1, len(numeric_features)))
                for i, feature in enumerate(numeric_features):
                    input_features[0, i] = float(input_company.get(feature, 0))
                
                # Scale input features
                input_features_scaled = scaler.transform(input_features)
                
                # Calculate similarity scores
                similarity_scores = cosine_similarity(input_features_scaled, company_features_scaled)[0]
                
                # Add similarity score to DataFrame
                size_filtered['similarity_score'] = similarity_scores
                
                # Sort by similarity score
                result = size_filtered.sort_values('similarity_score', ascending=False).head(top_n)
                
                logger.info(f"Returning top {len(result)} competitors by similarity score")
                return result
        
        # If we don't have financial metrics or can't calculate similarity,
        # just return the top companies from the filtered set
        if len(size_filtered) > top_n:
            logger.info(f"Returning top {top_n} competitors (without similarity scoring)")
            return size_filtered.head(top_n)
        else:
            logger.info(f"Returning all {len(size_filtered)} potential competitors")
            return size_filtered

def main():
    """
    Main function for testing competitor matching.
    """
    import os
    
    print("\n=== Competitor Matcher ===")
    print("Find similar companies to your private company")
    
    # Default path to company database
    db_path = os.path.join("./company_data", "company_database.csv")
    
    if not os.path.exists(db_path):
        print(f"\nError: Company database not found at {db_path}")
        print("Please run the database builder first to create a company database")
        return
    
    # Initialize the matcher
    matcher = CompetitorMatcher(db_path)
    
    # Get input company details
    print("\nEnter your company information:")
    company_name = input("Company name: ")
    industry = input("Industry: ")
    
    print("\nFinancial information (enter numbers without currency symbols or commas)")
    revenue_str = input("Annual revenue: ")
    revenue = float(revenue_str) if revenue_str else None
    
    employees_str = input("Number of employees: ")
    employees = int(employees_str) if employees_str else None
    
    profit_margin_str = input("Profit margin (% as decimal, e.g., 0.15 for 15%): ")
    profit_margin = float(profit_margin_str) if profit_margin_str else None
    
    # Create input company dict
    input_company = {
        "company_name": company_name,
        "industry": industry
    }
    
    if revenue is not None:
        input_company["revenue"] = revenue
    
    if employees is not None:
        input_company["employees"] = employees
    
    if profit_margin is not None:
        input_company["profit_margin"] = profit_margin
    
    # Find competitors
    competitors = matcher.find_competitors(input_company)
    
    if competitors.empty:
        print("\nNo competitors found")
        return
    
    # Display results
    print(f"\nTop competitors for {company_name}:")
    print("-" * 80)
    
    for idx, (_, company) in enumerate(competitors.iterrows(), 1):
        print(f"{idx}. {company['company_name']}")
        print(f"   Industry: {company['industry']}")
        print(f"   Country: {company.get('country', 'Unknown')}")
        
        if 'revenue' in company:
            print(f"   Revenue: {company['revenue']/1000000:.2f}M")
        
        if 'employees' in company:
            print(f"   Employees: {int(company['employees'])}")
        
        if 'profit_margin' in company:
            print(f"   Profit Margin: {company['profit_margin']*100:.2f}%")
        
        if 'similarity_score' in company:
            print(f"   Similarity Score: {company['similarity_score']:.2f}")
        
        print("-" * 80)
    
    print("\nAnalysis complete")

if __name__ == "__main__":
    main()