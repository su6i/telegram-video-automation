import json
import time
import re
from typing import List, Dict, Optional, Set
from datetime import datetime
from urllib.parse import urljoin
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
from .base import BaseScraper
import os
from dotenv import load_dotenv
from src import config

load_dotenv()

STORAGE_DIR = config.get_path("base_dir")
STRUCTURE_FILE = os.path.join(STORAGE_DIR, "course_structure.json")

class FatalScraperError(Exception):
    """Raised when a persistent network error occurs that should stop the scan."""
    pass

class PrimaryScraper(BaseScraper):
    def __init__(self):
        self.base_url = os.getenv("TARGET_SITE_BASE_URL")
        if not self.base_url:
             raise ValueError("TARGET_SITE_BASE_URL not found in .env")
             
        self.cookies_path = "auth_cookies.json"
        self.cookies = self._load_cookies()
        self.found_urls = set() # Standard deduplication within single run
        self.scanned_urls = set() # Global tracking to prevent recursion loops
        self.last_successful_lesson = "None"
        self.global_index = 0
        self._driver = None
        self.structure = [] # List of Course Objects
        
        # Load existing structure if available to append/resume
        if os.path.exists(STRUCTURE_FILE):
            try:
                with open(STRUCTURE_FILE, 'r', encoding='utf-8') as f:
                    self.structure = json.load(f)
            except: self.structure = []

    def get_video_links(self, limit=None, offset=0, callback=None):
        """
        Legacy compliance method for BaseScraper ABC.
        Redirects to Phased Scanning (Phase 2) if structure exists,
        or fails gracefully prompting for Phase 1.
        """
        print("⚠️  Deprecation Warning: 'get_video_links' is deprecated.")
        print("    Please use 'scan_structure' and 'scan_content' for better stability.")
        
        if not os.path.exists(STRUCTURE_FILE):
             print("❌ No structure found. Running Scan Structure first...")
             self.scan_structure()
             
        return self.scan_content(limit=limit, offset=offset, callback=callback)

    def _get_driver(self):
        """Returns the current driver, or creates a new one if it's dead/missing."""
        from selenium.common.exceptions import WebDriverException
        
        try:
            if self._driver:
                # Test the driver with a dummy call
                _ = self._driver.current_url
                return self._driver
        except WebDriverException:
            print("   ⚠️  Browser session lost. Re-initializing...")
            try: self._driver.quit()
            except: pass
            self._driver = None

        if not self._driver:
            chrome_options = Options()
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--disable-dev-shm-usage")
            
            # DEFAULT TO VISIBLE
            is_headless = os.getenv("HEADLESS_MODE", "false").lower() == "true"
            if is_headless:
                chrome_options.add_argument("--headless=new") 
                
            chrome_options.add_argument("--window-size=1920,1080")
            
            # USE PERSISTENT PROFILE
            profile_path = os.path.abspath(config.get_path("chrome_profile_dir"))
            os.makedirs(profile_path, exist_ok=True)
            chrome_options.add_argument(f"--user-data-dir={profile_path}")
            
            # CLEANUP LOCKS (Critical for "Chrome instance exited" error)
            lock_path = os.path.join(profile_path, "SingletonLock")
            if os.path.islink(lock_path) or os.path.exists(lock_path):
                try: os.unlink(lock_path)
                except: pass

            try:
                service = Service(ChromeDriverManager().install())
                self._driver = webdriver.Chrome(service=service, options=chrome_options)
            except Exception as e:
                print(f"   ❌ Failed to start Chrome: {e}")
                # Fallback to standard driver if profile is corrupt
                print("   🛠️ Attempting fallback with a clean profile...")
                self._driver = webdriver.Chrome(service=service)
            
            # ROBUST COOKIE INJECTION
            if self.cookies:
                print("   🍪 Syncing authentication cookies...")
                try:
                    # Set a short page load timeout for the initial hit
                    self._driver.set_page_load_timeout(30)
                    try:
                        self._driver.get(self.base_url)
                    except: 
                        print("   ⚠️  Cookie sync: Initial page load timed out (Continuing anyway...)")
                    
                    time.sleep(1)
                    
                    for cookie in self.cookies:
                        try: self._driver.add_cookie(cookie)
                        except: pass
                        
                    # Reset timeout to default
                    self._driver.set_page_load_timeout(300)
                    
                    try: self._driver.refresh()
                    except: pass
                    
                except Exception as e:
                     print(f"   ⚠️  Cookie Sync Skipped: {e}")
            
        return self._driver

    def _load_cookies(self):
        if not os.path.exists(self.cookies_path):
            return []
        with open(self.cookies_path, "r") as f:
            return json.load(f)

    def scan_structure(self, verbose=False):
        """PHASE 1: Scans the site hierarchy (Courses > Sections > Lessons) without fetching content."""
        print(f"🏗️  PHASE 1: Structural Discovery {'(VERBOSE)' if verbose else ''}")
        driver = self._get_driver()
        
        try:
            # 1. Domain Visit & Library Gate
            driver.get(f"{self.base_url}/library")
            time.sleep(3)
            
            # 2. Get All Courses
            courses = self._get_enrolled_courses()
            if not courses:
                print("❌ No courses found in library.")
                return []

            print(f"📚 Found {len(courses)} courses in library.")
            
            # 3. Iterate Courses
            for course_url in courses:
                self._discover_course_structure(driver, course_url, verbose)
            
            print("\n✅ Structural Discovery Complete.")
            print(f"📄 Saved structure to: {STRUCTURE_FILE}")
            
        finally:
            is_headless = os.getenv("HEADLESS_MODE", "false").lower() == "true"
            if is_headless:
                if self._driver: self._driver.quit()
            else:
                print("⚠️ Browser left open for debug.")

    def _discover_course_structure(self, driver, course_url, verbose=False):
        if course_url.endswith("/"): course_url = course_url[:-1]
        course_slug = course_url.split("/")[-1]
        
        # Determine Title
        course_title = course_slug.replace("-", " ").title()
        
        # Go to Categories
        cat_index_url = f"{course_url}/categories"
        print(f"\n🔹 Exploring Course: {course_title} ({cat_index_url})")
        
        driver.get(cat_index_url)
        time.sleep(3)
        
        # Title Extraction
        soup = BeautifulSoup(driver.page_source, "html.parser")
        extracted_title = self._extract_course_title(driver, soup)
        if extracted_title != "Unknown Course":
            course_title = extracted_title
            
        if verbose:
            print(f"   📘 Course Found: {course_title}")
        
        # Check if course exists in structure
        current_course_obj = next((c for c in self.structure if c['url'] == course_url), None)
        if not current_course_obj:
            current_course_obj = {
                "title": course_title,
                "url": course_url,
                "sections": []
            }
            self.structure.append(current_course_obj)
            self._save_structure_update()
            
        # Discover Sections (Categories)
        category_links = self._find_category_links(soup, course_url, cat_index_url)
        
        if category_links:
            print(f"   📂 Found {len(category_links)} Sections/Modules.")
            for cat_name, cat_url in category_links:
                self._discover_section_structure(driver, current_course_obj, cat_name, cat_url, verbose)
        else:
             print("   ⚠️ No categories/modules found. Scanning valid 'General' list.")
             # Treat entire course page as one 'General' section
             self._discover_section_structure(driver, current_course_obj, "General", driver.current_url, verbose)
             
        self._save_structure_update()

    def _discover_section_structure(self, driver, course_obj, section_name, section_url, verbose=False):
        if verbose: print(f"     📂 Section: {section_name}")
        
        # Check/Create Section Object
        current_section_obj = next((s for s in course_obj['sections'] if s['url'] == section_url), None)
        if not current_section_obj:
            current_section_obj = {
                "title": section_name,
                "url": section_url,
                "lessons": [] # List of {title, url, subsection}
            }
            course_obj['sections'].append(current_section_obj)
            self._save_structure_update()

        # Iterate Pages (Navigational Scan)
        current_page_url = section_url
        page_num = 1
        current_subsection = "General"
        
        visited_pages = set()
        
        while True:
            norm_url = current_page_url.rstrip("/").split("?")[0]
            if norm_url in self.scanned_urls:
                 if page_num == 1: break 
                 # If page 2+, check if we are looping
                 if current_page_url in visited_pages: break
            
            self.scanned_urls.add(norm_url)
            visited_pages.add(current_page_url)
            
            driver.get(current_page_url)
            time.sleep(2)
            soup = BeautifulSoup(driver.page_source, "html.parser")
            
            # Check for Sub-Categories (Recursion)
            sub_cat_links = []
            for a in soup.find_all("a", href=True):
                href = a['href']
                if "/categories/" in href and "/posts/" not in href:
                    full_sub = urljoin(current_page_url, href)
                    if full_sub.rstrip("/") != current_page_url.rstrip("/") and "/categories" not in href.split("/")[-1]:
                        sub_cat_links.append((a.get_text(strip=True), full_sub))
            
            if sub_cat_links:
                 if verbose: print(f"       ↳ Found {len(sub_cat_links)} Sub-Categories.")
                 for sub_name, sub_url in sub_cat_links:
                     # Flatten recursive sections to "Parent > Child"
                     full_name = f"{section_name} > {sub_name}"
                     self._discover_section_structure(driver, course_obj, full_name, sub_url, verbose)
            
            # Find Lesson Links (Leaf Nodes)
            lesson_links = self._extract_lesson_links_from_page(soup, driver.current_url)
            
            if lesson_links:
                 if verbose and page_num == 1: print(f"       ✅ Found {len(lesson_links)} lessons (Page {page_num})")
                 
                 # Process strictly to find "Subsections" (Headers)
                 for link_tag in lesson_links:
                     href = link_tag.get('href')
                     full_link = urljoin(self.base_url, href)
                     
                     # Extract Clean Title
                     clean_title = self._clean_lesson_title(link_tag)
                     if not clean_title: continue

                     # Deduplicate inside this section
                     if any(l['url'] == full_link for l in current_section_obj['lessons']):
                         continue

                     # Detect Sub-section header
                     found_subsection = self._detect_subsection(link_tag, course_obj['title'], section_name)
                     if found_subsection: current_subsection = found_subsection
                     
                     lesson_entry = {
                         "title": clean_title,
                         "url": full_link,
                         "subsection": current_subsection
                     }
                     current_section_obj['lessons'].append(lesson_entry)
                     
                     if verbose:
                         print(f"         📝 Lesson Found: {clean_title} [{current_subsection}]")
                         self._save_structure_update()
            
            # Pagination
            next_url = self._find_next_page(soup, current_page_url)
            if next_url and next_url not in visited_pages:
                 current_page_url = next_url
                 page_num += 1
                 if verbose: print(f"       ➡️  Going to Page {page_num}")
            else:
                 break
        
        self._save_structure_update()

    def _save_structure_update(self):
        """Atomically updates the structure file."""
        temp_file = STRUCTURE_FILE + ".tmp"
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(self.structure, f, indent=2, ensure_ascii=False)
        os.replace(temp_file, STRUCTURE_FILE)

    def _find_category_links(self, soup, course_url, cat_index_url):
        links = []
        seen = set()
        for a in soup.find_all("a", href=True):
            href = a['href']
            if "/categories/" in href and "/posts/" not in href:
                full_url = urljoin(course_url, href)
                if full_url.rstrip("/") == cat_index_url.rstrip("/") or full_url.rstrip("/") == course_url.rstrip("/"):
                    continue
                if full_url not in seen:
                    seen.add(full_url)
                    cat_name = a.get_text(strip=True) or "Unknown Category"
                    # Refine cat name
                    if cat_name.lower() in ["view module", "view category"]:
                         card = a.find_parent(class_="card")
                         if card: cat_name = card.select_one("h4, h5, .card__title").get_text(strip=True)
                    links.append((cat_name, full_url))
        return links

    def _extract_lesson_links_from_page(self, soup, page_url):
         # Valid Container Logic
         valid_links = []
         seen = set()
         
         # 1. Main Content Containers
         containers = soup.select(".main-content, #syllabus, .syllabus, .product-outline, .category-list, .panel__body, .panel-collapse, .course-curriculum, .category-outline")
         
         raw_links = []
         if containers:
             for c in containers:
                 if not (c.find_parent('aside') or c.find_parent(class_=['sidebar', 'main-sidebar'])):
                     raw_links.extend(c.select("a[href*='/posts/']"))
         else:
             # Fallback
             raw_links = soup.select("a[href*='/posts/']")
             
         for link in raw_links:
             if link.find_parent(['aside', 'nav']) or link.find_parent(class_=['sidebar', 'main-sidebar']):
                 continue
             href = link.get('href')
             if href and href not in seen:
                 seen.add(href)
                 valid_links.append(link)
         return valid_links

    def _detect_subsection(self, link_node, course_title, section_name):
        """Returns new subsection name if a header is found immediately preceding this link."""
        parent_item = link_node.find_parent(class_=lambda c: c and any(x in str(c).lower() for x in ["item", "card", "post"]))
        search_node = parent_item if parent_item else link_node
        
        # Look backwards
        header = search_node.find_previous(["h2", "h3", "h4", "h5", "div"], 
            class_=lambda c: c and any(x in str(c).lower() for x in ["title", "header", "section", "category", "heading", "accordion"]))
        
        if not header: header = search_node.find_previous(["h2", "h3", "h4"])
        
        if header:
            txt = header.get_text(strip=True)
            if 2 < len(txt) < 100:
                # Filter out generic titles
                lower_t = txt.lower()
                if lower_t not in [course_title.lower(), section_name.lower(), "videos", "lessons"]:
                    # Clean up
                    return re.sub(r'\(\d+.*?\)', '', txt).strip()
        return None

    def _clean_lesson_title(self, link_node):
        # Locate title inside link or parent
        title_node = link_node.select_one(".product-outline-post__title, p.syllabus__title, .post-title, .syllabus__item-title, .card__title")
        
        raw_text = ""
        if title_node:
             import copy
             t = copy.copy(title_node)
             for i in t.find_all(["svg", "i", "span"], class_=lambda c: c and any(x in str(c) for x in ["icon", "lesson-type"])): i.decompose()
             raw_text = t.get_text(separator=" ", strip=True)
        else:
             raw_text = link_node.get_text(separator=" ", strip=True)
             
        clean = re.sub(r'(?i)video lesson icon.*?Sketch\.?', '', raw_text.replace("\n", " ")).strip()
        if not clean or clean.lower() in ["start", "resume", "view", "watch", "next lesson"]: return None
        return clean

    def _find_next_page(self, soup, current_url):
        next_tag = soup.select_one(".pagination__next, a[rel='next'], a[aria-label='Next']")
        if next_tag:
             if next_tag.name == 'a': return urljoin(current_url, next_tag['href'])
             link = next_tag.find('a')
             if link: return urljoin(current_url, link['href'])
        
        # Text fallback
        for a in soup.find_all("a", href=True):
             if a.get_text(strip=True).lower() in ["next", "next page", "next >", ">"]:
                 return urljoin(current_url, a['href'])
        return None

    # --- SINGLE URL MODE ---
    def get_lesson_details(self, url):
        """Fetches a single lesson and attempts to extract full hierarchy metadata."""
        print(f"🔍 Analyzing Single URL: {url}")
        driver = self._get_driver()
        
        # 1. Navigate
        try:
            driver.get(url)
            time.sleep(3) # Wait for JS load
        except Exception as e:
            raise FatalScraperError(f"Failed to load URL: {e}")
        
        # 2. Extract Basic Content (Title, Video URL, Description)
        # We assume _extract_lesson_content works mainly on current page state
        data = self._extract_lesson_content(driver, url)
        
        # 3. Intelligent Hierarchy Extraction (Course > Section)
        # We need this to determine where to save the file
        soup = BeautifulSoup(driver.page_source, "html.parser")
        
        course_title = "Unknown Course"
        section_title = "General"
        
        # Strategy A: Breadcrumbs (Common in these platforms)
        # Look for typical breadcrumb structures
        breadcrumbs = soup.select("nav[aria-label='breadcrumb'] li, .breadcrumbs li, .breadcrumb-item")
        if breadcrumbs:
            texts = [b.get_text(strip=True) for b in breadcrumbs]
            # Valid breadcrumb usually: Home > Course Name > Section > Lesson
            # Or: Course Name > Section
            clean_texts = [t for t in texts if t not in ["Home", "Library", ">", "/"]]
            
            if len(clean_texts) >= 1:
                 course_title = clean_texts[0]
            if len(clean_texts) >= 2:
                 section_title = clean_texts[1]
                 
        # Strategy B: Sidebar / Product Outline
        # Try to find the 'active' lesson in the sidebar and look up to find the section header
        if section_title == "General":
            # Finding the active link in the sidebar
            active_node = soup.select_one(".product-outline-post.active, .sidebar .active, .lesson-item.active")
            if active_node:
                # Search backwards for a Section Header
                # Usually a div with class 'product-outline-category' or similar
                section_header = active_node.find_previous(class_=lambda c: c and any(x in str(c) for x in ["category-title", "section-title", "outline-category"]))
                if section_header:
                    header_text = section_header.select_one(".product-outline-category__title, h4, h5")
                    if header_text:
                        section_title = header_text.get_text(strip=True)
                    else:
                        section_title = section_header.get_text(strip=True)

        # Strategy B2: Panel Sub-Title (Confirmed by Browser Method)
        if section_title == "General":
            # Common in Kajabi themes: h5.panel__sub-title > a
            sub_title_link = soup.select_one("h5.panel__sub-title a, .panel__sub-title a, h5 a[href*='/categories/']")
            if sub_title_link:
                section_title = sub_title_link.get_text(strip=True)
            else:
                 # Direct Category Link anywhere near top
                 cat_link = soup.select_one("a[href*='/categories/']")
                 if cat_link:
                     section_title = cat_link.get_text(strip=True)

        # Strategy C: Page Title Fallback for Course
        if course_title == "Unknown Course":
             # 1. Product Link (Robust Kajabi Selector)
             # e.g. <a href='/products/ai-creator-course'>AI Creator Course</a>
             prod_link = soup.select_one("a[href^='/products/']:not([href*='/categories/']):not([href*='/posts/'])")
             if prod_link:
                 course_title = prod_link.get_text(strip=True)
             else:
                 # 2. Class-based fallback
                 c_title_tag = soup.select_one(".product-title, .course-title, .navbar-brand")
                 if c_title_tag:
                     course_title = c_title_tag.get_text(strip=True)
                 
        # Strategy D: URL Regex Fallback (Very reliable for this site)
        if course_title == "Unknown Course":
            import re
            # Extract from /products/ai-creator-course/...
            match = re.search(r'/products/([^/]+)', url)
            if match:
                slug = match.group(1)
                course_title = slug.replace("-", " ").title()
                # Specific Mapping
                if slug == "ai-creator-course":
                    course_title = "AI Creator Course"

        data['course_title'] = course_title
        data['section'] = section_title
        
        print(f"   📍 Context: {course_title} > {section_title}")
        return data

    # --- PHASE 2: CONTENT EXTRACTION ---
    def scan_content(self, limit=None, offset=0, callback=None):
        """PHASE 2: Hydrates the structure by visiting lesson URLs."""
        print("🏗️  PHASE 2: Content Extraction")
        
        if not os.path.exists(STRUCTURE_FILE):
             print("❌ No structure file found. Run with --scan-structure first.")
             return []
             
        with open(STRUCTURE_FILE, 'r', encoding='utf-8') as f:
            self.structure = json.load(f)
            
        driver = self._get_driver()
        collected_lessons = []
        
        # Flatten structure to a workable list
        work_queue = []
        for course in self.structure:
            for section in course['sections']:
                for lesson in section['lessons']:
                    # Enrich with parent data
                    lesson_copy = lesson.copy()
                    lesson_copy['course_title'] = course['title']
                    lesson_copy['section'] = section['title']
                    lesson_copy['category'] = section['title']
                    work_queue.append(lesson_copy)
        
        print(f"📦 Total Lessons in Queue: {len(work_queue)}")
        
        # Offset handling
        if offset > 0:
            print(f"⏭️  Skipping first {offset} lessons.")
            work_queue = work_queue[offset:]
            
        count = 0
        for lesson_item in work_queue:
            if limit and count >= limit: break
            
            print(f"   🎥 Fetching: {lesson_item['title']}...")
            try:
                # Hydrate
                data = self._extract_lesson_content(driver, lesson_item['url'], default_title=lesson_item['title'])
                if data:
                    # Merge Structure Data
                    data.update({
                        'course_title': lesson_item['course_title'],
                        'category': lesson_item['category'],
                        'section': lesson_item['section'],
                        'subsection': lesson_item['subsection']
                    })
                    
                    collected_lessons.append(data)
                    count += 1
                    
                    if callback: callback(data)
                    
            except FatalScraperError: raise
            except Exception as e:
                print(f"   ❌ Error extracting content: {e}")
                
        return collected_lessons

    # --- EXISTING HELPER METHODS ---
    def _get_enrolled_courses(self) -> List[str]:
        library_url = f"{self.base_url}/library"
        while True:
            driver = self._get_driver()
            try:
                driver.get(library_url)
                time.sleep(3)
                curr_url = driver.current_url.lower()
                page_source = driver.page_source.lower()
                
                if "/products/" in page_source or "my products" in page_source or "/library" in curr_url:
                    break
                
                print(f"🚨 AUTH CHECKPOINT: {driver.title}")
                input("⌨️  Please solve auth/captcha in browser and press ENTER: ")
            except Exception as e:
                print(f"   Session error: {e}")
                time.sleep(2)

        soup = BeautifulSoup(driver.page_source, "html.parser")
        course_links = set()
        for a_tag in soup.find_all("a", href=True):
            href = a_tag["href"]
            if "/products/" in href and "/categories/" not in href and "/posts/" not in href:
                full_url = self.base_url + href if href.startswith("/") else href
                course_links.add(full_url)
        return sorted(list(course_links))

    def _extract_course_title(self, driver, soup):
        course_title = "Unknown Course"
        title_tag = soup.select_one(".product-title h1")
        if title_tag:
            course_title = title_tag.get_text(strip=True)
        if course_title == "Unknown Course":
            title_tag = soup.select_one(".hero__title") or soup.select_one("h1.hero-title") or soup.select_one("h1")
            if title_tag:
                 course_title = title_tag.get_text(strip=True)
        
        mapping = {
            "Become a Content Creator | Worlds Best Online Course & Apprenticeships": "AI Creator Course",
            "become-a-content-creator-worlds-best-online-course-apprenticeships": "AI Creator Course"
        }
        return mapping.get(course_title, course_title)

    def _extract_lesson_content(self, driver, lesson_url, default_title=None):
        # Robust navigation with retries
        max_retries = 3
        for i in range(max_retries):
            try:
                driver.get(lesson_url)
                if driver.current_url != "about:blank": break
            except Exception as e:
                if i == max_retries - 1: raise FatalScraperError(f"Connection Failed: {e}")
                time.sleep(2)
        
        time.sleep(1.5)
        soup = BeautifulSoup(driver.page_source, "html.parser")
        
        # Title Logic
        final_title = default_title or "Unknown Title"
        
        # Priority 1: Specific Lesson Title Element
        title_el = soup.select_one(".post-title, .product-outline-post__title, h1.title, .lesson_title")
        if title_el:
             final_title = title_el.get_text(strip=True)
        # Priority 2: Generic H1 if mostly unique
        elif not default_title:
             h1 = soup.find("h1")
             if h1: final_title = h1.get_text(strip=True)
        # Priority 3: Meta Title Fallback
        elif not default_title:
             final_title = driver.title.split("|")[0].strip()
        
        # Extract Content Body (Simplified for this file re-write, but core logic preserved)
        body_content = ""
        extracted_links = []
        
        # Look for content containers
        div = soup.select_one(".post-body, .user-content, .content-wrap, .product-outline-post__text")
        if div:
            # 1. Links
            for a in div.find_all("a", href=True):
                 link_url = urljoin(lesson_url, a['href'])
                 if link_url.startswith("http") and "/products/" not in link_url:
                     extracted_links.append({"text": a.get_text(strip=True), "url": link_url})
            # 2. Text
            body_content = div.get_text(separator="\n", strip=True)
            
        page_source = driver.page_source
        wistia_id = None
        # Pattern 1: Standard iframe embed
        iframe_match = re.search(r'fast\.wistia\.(?:com|net)/embed/iframe/([a-zA-Z0-9]+)', page_source)
        if iframe_match: wistia_id = iframe_match.group(1)
        
        # Return Lesson Data
        return {
            "title": final_title,
            "url": f"https://fast.wistia.net/embed/iframe/{wistia_id}" if wistia_id else None,
            "course_url": lesson_url,
            "description": body_content, 
            "links": extracted_links,
            "html": driver.page_source
        }
