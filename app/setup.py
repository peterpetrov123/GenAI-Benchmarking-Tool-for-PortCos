#!/usr/bin/env python3
"""
Setup script for the Financial Competitor Finder Web Application
This script creates the necessary directory structure and sets up the environment.
"""

import os
import shutil
import sys
from pathlib import Path

def create_directory_structure():
    """Create the necessary directory structure for the application"""
    print("Creating directory structure...")
    
    # Create directories if they don't exist
    directories = [
        'templates',
        'test_data',
        'financial_data',
        'financial_data/processed',
        'competitor_analysis'
    ]
    
    for directory in directories:
        os.makedirs(directory, exist_ok=True)
        print(f"✓ Created directory: {directory}")
    
    # Create .env file from template if it doesn't exist
    if not os.path.exists('.env') and os.path.exists('.env.template'):
        shutil.copy('.env.template', '.env')
        print("✓ Created .env file from template. Please update with your API keys.")
    
    print("\nDirectory structure created successfully!")

def check_required_files():
    """Check if all required files are present"""
    print("\nChecking required files...")
    
    required_files = [
        'app.py',
        'templates/base.html',
        'templates/index.html',
        'templates/results.html',
        'Dockerfile',
        'docker-compose.yml',
        'requirements.txt'
    ]
    
    missing_files = []
    for file in required_files:
        if not os.path.exists(file):
            missing_files.append(file)
    
    if missing_files:
        print("❌ Missing required files:")
        for file in missing_files:
            print(f"  - {file}")
        return False
    
    print("✓ All required files are present.")
    return True

def check_src_directory():
    """Check if the src directory has the required scripts"""
    print("\nChecking src directory...")
    
    if not os.path.exists('src'):
        print("❌ src directory not found!")
        return False
    
    required_scripts = [
        'main.py',
        'azure_processing.py',
        'blob_storage.py'
    ]
    
    missing_scripts = []
    for script in required_scripts:
        if not os.path.exists(os.path.join('src', script)):
            missing_scripts.append(script)
    
    if missing_scripts:
        print("❌ Missing required scripts in src directory:")
        for script in missing_scripts:
            print(f"  - {script}")
        return False
    
    print("✓ src directory contains required scripts.")
    return True

def main():
    """Main function to run the setup process"""
    print("=" * 60)
    print("Financial Competitor Finder Web Application Setup".center(60))
    print("=" * 60)
    
    create_directory_structure()
    
    files_ok = check_required_files()
    src_ok = check_src_directory()
    
    if not files_ok or not src_ok:
        print("\n❌ Setup incomplete. Please address the issues above.")
        return 1
    
    print("\n✅ Setup completed successfully!")
    print("\nNext steps:")
    print("1. Update the .env file with your API keys")
    print("2. Run the application with: docker-compose up -d --build")
    print("3. Access the web interface at: http://localhost:5000")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())