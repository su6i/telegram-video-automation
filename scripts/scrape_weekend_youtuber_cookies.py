#!/usr/bin/env python3
"""
Scrape Weekend Youtuber using session/cookies from auth_cookies.json
"""

import json
import requests
from bs4 import BeautifulSoup
import time

def scrape_with_cookies(url, cookies_file):
    """
    Scrape page using saved cookies
    """
    
    # Load cookies
    try:
        with open(cookies_file, 'r') as f:
            cookies_data = json.load(f)
        print(f"✅ Loaded cookies from {cookies_file}")
    except FileNotFoundError:
        print(f"❌ Cookie file not found: {cookies_file}")
        return None
    
    # Convert cookies to requests format
    session = requests.Session()
    
    # Add cookies to session
    if isinstance(cookies_data, dict) and 'cookies' in cookies_data:
        for cookie in cookies_data['cookies']:
            session.cookies.set(cookie.get('name'), cookie.get('value'))
    elif isinstance(cookies_data, dict):
        for key, value in cookies_data.items():
            session.cookies.set(key, value)
    
    # Add headers
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
    }
    
    try:
        print(f"Fetching {url}...")
        response = session.get(url, headers=headers, timeout=15)
        
        if response.status_code != 200:
            print(f"❌ Status code: {response.status_code}")
            return None
        
        print(f"✅ Page loaded (status 200)")
        
        # Parse HTML
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Look for section structure
        sections = soup.find_all(['section', 'div'], class_=lambda x: x and 'section' in x.lower())
        
        print(f"\nFound {len(sections)} potential section elements")
        
        # Extract course structure
        course_structure = {}
        
        # Try different selectors
        for selector in ['.curriculum-section', '.section-module', 'h2', 'h3']:
            elements = soup.select(selector)
            if elements:
                print(f"Found {len(elements)} elements with selector: {selector}")
        
        # Print first 2000 chars of HTML to understand structure
        print("\n--- HTML STRUCTURE (first 3000 chars) ---")
        print(response.text[:3000])
        
        return soup
    
    except Exception as e:
        print(f"❌ Error: {e}")
        return None

def main():
    cookies_file = "/Users/su6i/@-github/telegram-video-automation/auth_cookies.json"
    url = "https://www.contentcreator.com/products/weekend-youtuber/categories"
    
    print("=" * 80)
    print("SCRAPING: Weekend Youtuber (using cookies)")
    print("=" * 80)
    
    soup = scrape_with_cookies(url, cookies_file)

if __name__ == "__main__":
    main()
