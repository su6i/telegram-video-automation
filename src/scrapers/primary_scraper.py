import json
import time
import re
from typing import List, Dict, Optional
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
from .base import BaseScraper
import os
from dotenv import load_dotenv

load_dotenv()

class PrimaryScraper(BaseScraper):
    def __init__(self):
        self.base_url = os.getenv("TARGET_SITE_BASE_URL")
        if not self.base_url:
             raise ValueError("TARGET_SITE_BASE_URL not found in .env")
             
        # Optional: default course if needed, but we scan library now
        self.course_url = f"{self.base_url}/products/ai-creator-course"
        self.cookies_path = "auth_cookies.json"
        self.cookies = self._load_cookies()

    def _load_cookies(self):
        if not os.path.exists(self.cookies_path):
            print(f"Warning: {self.cookies_path} not found. Authentication might fail.")
            return []
        with open(self.cookies_path, "r") as f:
            return json.load(f)

    def get_video_links(self, limit: Optional[int] = None, callback=None) -> List[Dict]:
        print("Initializing Browser for Scraper...")
        
        chrome_options = Options()
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--headless=new") 
        chrome_options.add_argument("--window-size=1920,1080")

        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        
        all_videos = []
        try:
            # 1. Domain Visit & Cookie Injection
            driver.get(self.base_url) 
            for cookie in self.cookies:
                try:
                    driver.add_cookie(cookie)
                except Exception:
                    pass
            
            # 2. Get All Courses
            courses = self._get_enrolled_courses(driver)
            if not courses:
                print("❌ No courses found in library.")
                return []

            print(f"📚 Found {len(courses)} courses in library.")

            # 3. Iterate Courses
            for course_url in courses:
                print(f"🔹 Scanning Course: {course_url}")
                course_videos = self._scan_course(driver, course_url, limit, callback)
                all_videos.extend(course_videos)
                
                if limit and len(all_videos) >= limit:
                    break

        finally:
            driver.quit()
            
        return all_videos

    def _get_enrolled_courses(self, driver) -> List[str]:
        """Scrapes the /library page for all enrolled course URLs."""
        library_url = f"{self.base_url}/library"
        print(f"Navigating to Library: {library_url}")
        driver.get(library_url)
        time.sleep(5)

        if "/login" in driver.current_url:
            print("❌ Error: Redirected to login page. Cookies might be expired.")
            return []

        soup = BeautifulSoup(driver.page_source, "html.parser")
        
        # Kajabi library usually has product cards. 
        # We look for links containing '/products/' ignoring specific post links.
        # usually: <a href="/products/some-course-slug">
        course_links = set()
        for a_tag in soup.find_all("a", href=True):
            href = a_tag["href"]
            # Exclude specific posts/categories, just want the main product page
            # Product URL pattern: /products/course-slug
            # Avoid: /products/course-slug/categories/...
            if "/products/" in href and "/categories/" not in href and "/posts/" not in href:
                full_url = self.base_url + href if href.startswith("/") else href
                course_links.add(full_url)
        
        return sorted(list(course_links))

    def _scan_course(self, driver, course_url, limit=None, callback=None) -> List[Dict]:
        """Scans a single course page for videos."""
        driver.get(course_url)
        time.sleep(3)
        
        soup = BeautifulSoup(driver.page_source, "html.parser")
        
        # DEBUG: Save source to inspect structure
        with open("debug_course_source.html", "w", encoding="utf-8") as f:
            f.write(soup.prettify())
        print(f"   🐛 Saved debug source to debug_course_source.html")
        
        # Extract Course Title
        course_title = "Unknown Course"
        
        # Try Selector 1 (Outline Layout)
        title_tag = soup.select_one(".product-title h1")
        if title_tag:
            course_title = title_tag.get_text(strip=True)
        
        # Try Selector 2 (Syllabus Layout / Hero)
        if course_title == "Unknown Course":
            title_tag = soup.select_one(".hero__title") or soup.select_one("h1.hero-title") or soup.select_one("h1")
            if title_tag:
                 course_title = title_tag.get_text(strip=True)
        
        # Fallback: Page Title (cleanup known suffixes)
        if course_title == "Unknown Course" or len(course_title) > 50:
            page_title = driver.title.strip()
            # Remove common suffixes if present
            for suffix in [" | Content Creator", " - Content Creator", " | Kajabi"]:
                page_title = page_title.replace(suffix, "")
            course_title = page_title
            
        print(f"   ℹ️ Course Identified: '{course_title}'")
        
        # Strategy 1: Standard Syllabus (AI Creator Course style)
        lesson_items = soup.select("div.syllabus__item a")
        selector_type = "syllabus"
        
        # Strategy 2: Product Outline (Weekend YouTuber style)
        if not lesson_items:
            lesson_items = soup.select("a.product-outline-post")
            selector_type = "outline"
        
        if not lesson_items:
            print(f"⚠️ No lessons found for {course_url}")
            return []
        
        print(f"   found {len(lesson_items)} lessons in '{course_title}' (Type: {selector_type}). Extracting videos...")
        videos = []
        
        for i, link in enumerate(lesson_items):
            if limit and len(videos) >= limit:
                break
            
            href = link.get("href")
            if not href:
                continue
            
            full_link = self.base_url + href if href.startswith("/") else href
            
            # --- Extract Section / Module Title ---
            # Simplified Strategy: Find the nearest preceding element that looks like a section header.
            # This works for both nested and linear layouts.
            section_title = "General"
            
            # Look for standard Kajabi section classes appearing before this link
            # Updated to 'syllabus__heading' based on debug source analysis
            prev_section_node = link.find_previous(class_=lambda c: c and ("syllabus__heading" in c or "syllabus__section-title" in c or "product-outline-category__title" in c))
            
            if prev_section_node:
                section_title = prev_section_node.get_text(strip=True)
            else:
                 # Fallback for very weird layouts: Look for any H4/H5 with 'title' in class
                 prev_header = link.find_previous(["h4", "h5", "div"], class_=lambda c: c and "title" in c and "section" in c)
                 if prev_header:
                     section_title = prev_header.get_text(strip=True)

            # Capture visible text
            title_candidate = link.select_one(".product-outline-post__title, .syllabus__title, .post-title, .syllabus__item-title")
            
            if title_candidate:
                raw_text = title_candidate.get_text(separator=" ", strip=True)
            else:
                raw_text = link.get_text(separator=" ", strip=True) 
            
            # Clean up known dirty icon text (Handle both cases: no space and space)
            clean_text = raw_text.replace("video lesson icon/defaultCreated with Sketch.", "")
            clean_text = clean_text.replace("video lesson icon/default Created with Sketch.", "")
            clean_text = clean_text.replace("\n", " ").replace("\r", " ")
            
            # Collapse multiple spaces
            clean_text = re.sub(r'\s+', ' ', clean_text).strip()
            
            # Remove Section Name from Title if redundant (e.g. "Clone Yourself - CapCut Desktop")
            if section_title != "General" and section_title in clean_text:
                # Remove " - Section Name" or just "Section Name" at end
                clean_text = clean_text.replace(f" - {section_title}", "")
                clean_text = clean_text.replace(section_title, "").strip()
                # Clean stray usage like " | " at end
                clean_text = clean_text.rstrip("| -")

            lesson_title_from_syllabus = clean_text
            
            try:
                # Pass clean title AND section data
                video_data = self._extract_lesson_video(driver, full_link, default_title=lesson_title_from_syllabus)
                if video_data:
                    video_data['course_title'] = course_title 
                    video_data['section'] = section_title 
                    video_data['total_course_lessons'] = len(lesson_items) 
                    videos.append(video_data)
                    print(f"   ✅ Found: {video_data['title']} (In: {section_title})")
                    
                    if callback:
                        callback(video_data)
                else:
                    pass
                
                time.sleep(0.5)
                
            except Exception as e:
                print(f"   ❌ Error extracting {full_link}: {e}")

        return videos

    def _extract_lesson_video(self, driver, lesson_url, default_title=None):
        driver.get(lesson_url)
        # Faster wait - we just need source
        # time.sleep(2) 
        # Actually Wistia iframe might take a moment to inject into DOM, but 'page_source' 
        # often contains the async script immediately.
        time.sleep(1.5) 
        
        soup = BeautifulSoup(driver.page_source, "html.parser")
        
        # Strategy:
        # 0. Syllabus Link Text (Passed as default_title). This is the gold standard.
        # 1. <title> tag.
        # 2. H1 tags.
        
        final_title = "Unknown Title"
        
        if default_title and len(default_title) > 2 and default_title.lower() != "start":
            final_title = default_title
        else:
            # Fallback to scraping logic if syllabus text was garbage
            page_title = driver.title.strip()
            
            # Cleanup page title
            clean_title = page_title
            for suffix in [" | Content Creator", " - Content Creator", " | Kajabi"]:
                clean_title = clean_title.replace(suffix, "")
            
            if len(clean_title) > 3 and "Content Creator" not in clean_title:
                 final_title = clean_title
            else:
                 # Last resort DOM scraping
                 title_tag = soup.select_one("h1.post-title") or \
                            soup.select_one("span.post-title") or \
                            soup.select_one(".product-outline-post.active .media-body")
                 
                 if title_tag:
                     final_title = title_tag.get_text(strip=True)
        
        page_source = driver.page_source
        
        wistia_id = None
        iframe_match = re.search(r'fast\.wistia\.(?:com|net)/embed/iframe/([a-zA-Z0-9]+)', page_source)
        if iframe_match:
            wistia_id = iframe_match.group(1)
        
        if not wistia_id:
            script_match = re.search(r'async src="https://fast\.wistia\.com/embed/medias/([a-zA-Z0-9]+)\.jsonp"', page_source)
            if script_match:
                wistia_id = script_match.group(1)
        
        if wistia_id:
            return {
                "title": final_title,
                "url": f"https://fast.wistia.net/embed/iframe/{wistia_id}",
                "date": None,
                "course_url": lesson_url # Tracking origin might be nice
            }
        
        return None
