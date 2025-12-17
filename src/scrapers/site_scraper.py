import requests
from bs4 import BeautifulSoup
import json
from urllib.parse import parse_qs, urlparse
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
import time
from datetime import datetime
import threading
from .base import BaseScraper

class SiteScraper(BaseScraper):
    """
    Example implementation of a site scraper.
    Customize this class to scrape your target website.
    """
    def __init__(self):
        # Base URL of the target site
        self.base_url = "https://example.com"  # Replace with actual target
        self.one_part_url = self.base_url + "/one_part/"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        self.print_lock = threading.Lock()

    def _log(self, message):
        with self.print_lock:
            print(message)

    def get_video_links(self, limit: int = None) -> list:
        """Scrapes all video links from Mongard."""
        subpage_links = self._get_subpage_links()
        if not subpage_links:
            self._log("No subpages found!")
            return []

        self._log(f"Found {len(subpage_links)} subpages. Extracting video URLs...")
        
        videos = []
        for i, subpage_url in enumerate(subpage_links):
            if limit and i >= limit:
                break
            try:
                video_data = self._extract_video_data(subpage_url)
                if video_data:
                    videos.append(video_data)
                    self._log(f"Extracted: {video_data['title']} ({video_data['date']})")
                else:
                    self._log(f"No video found in {subpage_url}")
                time.sleep(1) # Rate limiting
            except Exception as e:
                self._log(f"Error processing {subpage_url}: {str(e)}")

        # Sort by date (Oldest First)
        # If date is missing, we might rely on the scraping order (assuming site lists Newest First, so we might reverse)
        # But let's sort primarily by date.
        videos.sort(key=lambda x: x['date'] if x['date'] else datetime.min)
        
        return videos

    def _get_subpage_links(self):
        subpage_links = []
        page = 1
        while True:
            url = f"{self.one_part_url}?page={page}" if page > 1 else self.one_part_url
            self._log(f"Checking page {page}: {url}")
            try:
                response = requests.get(url, headers=self.headers, timeout=10)
                response.raise_for_status()
                soup = BeautifulSoup(response.text, "html.parser")
                cards = soup.find_all("div", class_="card")
                
                if not cards:
                    self._log(f"Page {page} is empty. Stopping.")
                    break

                new_links = 0
                for card in cards:
                    link = card.find("a", href=True)
                    if link and "/one_part/" in link["href"]:
                        full_link = self.base_url + link["href"] if link["href"].startswith("/") else link["href"]
                        if full_link not in subpage_links:
                            subpage_links.append(full_link)
                            new_links += 1
                
                if new_links == 0:
                    self._log(f"No new links on page {page}. Stopping.")
                    break
                
                page += 1
                time.sleep(1)
            except Exception as e:
                self._log(f"Error getting page {page}: {str(e)}")
                break
        return subpage_links

    def _extract_video_data(self, subpage_url):
        title = "unknown"
        video_url = None
        published_date = None

        chrome_options = Options()
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        # Assuming chromedriver is in path or managed by selenium manager in newer versions
        # logic from main.py
        service = Service("/usr/local/bin/chromedriver") 
        driver = webdriver.Chrome(service=service, options=chrome_options)

        try:
            driver.get(subpage_url)
            time.sleep(3)
            soup = BeautifulSoup(driver.page_source, "html.parser")

            title_tag = soup.find("h1", class_="blog-title")
            title = title_tag.text.strip().replace("ویدیو ", "") if title_tag else "unknown_video"

            # Extract Date from JSON-LD
            json_ld = soup.find("script", type="application/ld+json")
            if json_ld:
                try:
                    json_data = json.loads(json_ld.text)
                    # Try standard schema.org fields
                    date_str = json_data.get("datePublished") or json_data.get("uploadDate")
                    if date_str:
                        # Handle different date formats if necessary. ISO 8601 is standard.
                        # e.g. 2023-10-27T10:00:00+03:30
                        published_date = datetime.fromisoformat(date_str)
                    
                    # ALSO check embedUrl logic from main.py
                    embed_url = json_data.get("embedUrl", "")
                    if not video_url:
                        video_url = self._extract_m3u8_from_arvan(embed_url)

                except Exception as e:
                    self._log(f"Error parsing JSON-LD: {e}")

            # Fallback to iframe if no video_url yet
            if not video_url:
                iframe = soup.find("iframe", src=True)
                if iframe:
                    video_url = self._extract_m3u8_from_arvan(iframe["src"])

            return {
                "title": title,
                "url": video_url,
                "date": published_date
            }

        except Exception as e:
            self._log(f"Error extraction video from {subpage_url}: {e}")
            return None
        finally:
            driver.quit()

    def _extract_m3u8_from_arvan(self, url):
        if not url or "player.arvancloud.ir" not in url:
            return None
        
        try:
            parsed_url = urlparse(url)
            query_params = parse_qs(parsed_url.query)
            config_url = query_params.get("config", [None])[0]
            
            if config_url and config_url.endswith(".json"):
                config_response = requests.get(config_url, headers=self.headers)
                config_response.raise_for_status()
                config_data = json.loads(config_response.text)
                
                if "source" in config_data and isinstance(config_data["source"], list):
                    for source in config_data["source"]:
                        if source.get("type") == "application/x-mpegURL":
                            return source.get("src")
        except Exception as e:
            self._log(f"Error extracting Arvan link: {e}")
        return None
