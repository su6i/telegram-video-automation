import json
import time
import re
from typing import List, Dict, Optional
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

load_dotenv()

class PrimaryScraper(BaseScraper):
    def __init__(self):
        self.base_url = os.getenv("TARGET_SITE_BASE_URL")
        if not self.base_url:
             raise ValueError("TARGET_SITE_BASE_URL not found in .env")
             
        self.course_url = f"{self.base_url}/products/ai-creator-course"
        self.cookies_path = "auth_cookies.json"
        self.cookies = self._load_cookies()
        self.found_urls = set() # Global deduplication within a run

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
        
        # Headless control via Env Var (Default: True)
        if os.getenv("HEADLESS_MODE", "true").lower() == "true":
            chrome_options.add_argument("--headless=new") 
        else:
            # Keep window open in visible mode
            chrome_options.add_experimental_option("detach", True)
            
        chrome_options.add_argument("--window-size=1920,1080")

        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        
        all_videos = []
        try:
            # 1. Domain Visit & Cookie Injection
            driver.get(self.base_url) 
            # 1. Domain Visit
            driver.get(self.base_url) 
            
            # DISABLE COOKIE INJECTION (Process manual login only)
            # for cookie in self.cookies:
            #     try:
            #         driver.add_cookie(cookie)
            #     except Exception:
            #         pass
            
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
            # Only quit if headless or if user didn't request detach
            if os.getenv("HEADLESS_MODE", "true").lower() == "true":
                driver.quit()
            else:
                print("⚠️ Browser left open for debugging (visible mode). Close manually when done.")
            
        return all_videos

    def _get_enrolled_courses(self, driver) -> List[str]:
        """Scrapes the /library page for all enrolled course URLs."""
        library_url = f"{self.base_url}/library"
        print(f"Navigating to Library: {library_url}")
        driver.get(library_url)
        time.sleep(5)

        # Check via Title OR Page Content
        page_source = driver.page_source.lower()
        if "/login" in driver.current_url or "rejected" in driver.title.lower() or "change you wanted was rejected" in page_source:
            print("\n🚨 AUTH CHECKPOINT DETECTED! 🚨")
            print("The scraper is stuck on the Login or Error page.")
            print("👉 ACTION REQUIRED (Since you are in visible mode):")
            print("1. Switch to the Browser Window.")
            print("2. Navigate to the login page (if stuck on error).")
            print("3. Log in manually / Solve Cloudflare Challenge.")
            print("4. Wait until you see the 'Library' page.")
            print("5. Come back here and press ENTER.")
            
            while "/login" in driver.current_url or "rejected" in driver.title.lower() or "change you wanted was rejected" in driver.page_source.lower():
                input("\n⌨️  Press ENTER after you have successfully logged in... ")
                time.sleep(2)
        
        # Double check where we are
        if "/library" not in driver.current_url and "/products" not in driver.current_url:
             print(f"⚠️ Warning: Current URL is {driver.current_url}. Trying to proceed anyway...")

        soup = BeautifulSoup(driver.page_source, "html.parser")
        
        course_links = set()
        for a_tag in soup.find_all("a", href=True):
            href = a_tag["href"]
            if "/products/" in href and "/categories/" not in href and "/posts/" not in href:
                full_url = self.base_url + href if href.startswith("/") else href
                course_links.add(full_url)
        
        return sorted(list(course_links))

    def _scroll_to_bottom(self, driver, max_scrolls=10):
        """Scrolls to the bottom of the page to trigger lazy loading."""
        last_height = driver.execute_script("return document.body.scrollHeight")
        for i in range(max_scrolls):
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)
            new_height = driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                break
            last_height = new_height

    def _scan_course(self, driver, course_url, limit=None, callback=None) -> List[Dict]:
        """Scans a course systematically by going directly to /categories."""
        if course_url.endswith("/"): course_url = course_url[:-1]
        
        # Extract course slug to identify course
        # e.g. https://example.com/products/course-name
        course_slug = course_url.split("/")[-1]
        
        # User Instruction: Go DIRECTLY to categories page
        # e.g. .../products/ai-creator-course/categories
        cat_index_url = f"{course_url}/categories"
        
        print(f"   ℹ️ Target Course: {course_slug}")
        print(f"   🔍 Navigating to Categories Index: {cat_index_url}")
        
        driver.get(cat_index_url)
        time.sleep(3)
        self._scroll_to_bottom(driver, max_scrolls=2)
        
        # Check if we landed on a login page or were redirected
        if "/login" in driver.current_url:
             print("   ❌ Redirected to login. Session might be invalid.")
             return []
        
        # Attempt to get course title from the categories page
        soup = BeautifulSoup(driver.page_source, "html.parser")
        course_title = self._extract_course_title(driver, soup)
        if course_title == "Unknown Course" and course_slug:
             course_title = course_slug.replace("-", " ").title()
        
        print(f"   📘 Course Title: {course_title}")

        # Extract Category links (Modules)
        # Look for links containing /categories/ID
        category_links = []
        seen_cat_urls = set()
        
        # Specific selector for generic platform themes usually listing categories
        # We look for a tags that have "/categories/" in href, but NOT invalid ones
        potential_links = soup.find_all("a", href=True)
        
        for a in potential_links:
            href = a['href']
            if "/categories/" in href and "/posts/" not in href:
                full_url = urljoin(course_url, href)
                
                # Exclude the index page itself
                if full_url.rstrip("/") == cat_index_url.rstrip("/"):
                    continue
                
                # Exclude "Back to Course" links if they point to course_url
                if full_url.rstrip("/") == course_url.rstrip("/"):
                    continue
                
                if full_url not in seen_cat_urls:
                    seen_cat_urls.add(full_url)
                    
                    # Extract Category Name
                    # Try to find a heading inside the <a> or previous sibling
                    cat_name = a.get_text(strip=True)
                    
                    # If text is generic like "View Category", look for a title nearby
                    if not cat_name or cat_name.lower() in ["view category", "view module", "start", "resume"]:
                        # Try finding a card title
                        card = a.find_parent(class_="card") or a.find_parent(class_="category-list__item")
                        if card:
                            title_node = card.select_one(".category-list__title, .card__title, h4, h5")
                            if title_node:
                                cat_name = title_node.get_text(strip=True)
                    
                    if not cat_name:
                        cat_name = f"Category {len(category_links) + 1}"
                        
                    category_links.append((cat_name, full_url))
        
        all_videos = []
        
        if category_links:
            print(f"   📁 Found {len(category_links)} categories/modules. Starting recursion.")
            for idx, (cat_name, cat_url) in enumerate(category_links, 1):
                if limit and len(all_videos) >= limit: break
                
                print(f"   📂 [{idx}/{len(category_links)}] Scanning Category: {cat_name}")
                print(f"       🔗 URL: {cat_url}")
                
                # Scan the Category Page (Post List)
                # Pass the category name as the default section
                cat_videos = self._scan_page_posts(driver, cat_url, course_title, limit, callback, default_section=cat_name)
                print(f"       ✅ Found {len(cat_videos)} videos in '{cat_name}'")
                all_videos.extend(cat_videos)
        else:
            print(f"   ⚠️ No categories found on {cat_index_url}")
            print(f"   📄 Scanning the page itself as a potential single-list course.")
            all_videos = self._scan_page_posts(driver, driver.current_url, course_title, limit, callback, default_section="General")
            
        return all_videos

    def _extract_course_title(self, driver, soup):
        course_title = "Unknown Course"
        title_tag = soup.select_one(".product-title h1")
        if title_tag:
            course_title = title_tag.get_text(strip=True)
        if course_title == "Unknown Course":
            title_tag = soup.select_one(".hero__title") or soup.select_one("h1.hero-title") or soup.select_one("h1")
            if title_tag:
                 course_title = title_tag.get_text(strip=True)
        if course_title == "Unknown Course" or len(course_title) > 50:
            page_title = driver.title.strip()
            for suffix in [" | Platform", " - Platform", " | Service"]:
                page_title = page_title.replace(suffix, "")
            course_title = page_title
        return course_title

    def _scan_page_posts(self, driver, url, course_title, limit=None, callback=None, default_section=None):
        """Scans a specific page (Category) for posts, handles pagination and sub-sections."""
        videos = []
        visited_pages = set()
        
        current_page_url = url
        page_number = 1
        
        # The 'default_section' passed here is actually the CATEGORY (Module) name
        category_name = default_section or "General"
        
        while True:
            if current_page_url in visited_pages:
                print(f"     ⏭️ Already visited this page, stopping pagination")
                break
            visited_pages.add(current_page_url)
            
            # Reset subsection for each page? No, subsections might span pages, but usually page breaks interrupt flow.
            # Best to reset "current_subsection" to None unless we track it
            current_subsection = "General" 
            
            print(f"     📄 Fetching Page {page_number}: {current_page_url}")
            driver.get(current_page_url)
            time.sleep(3)
            soup = BeautifulSoup(driver.page_source, "html.parser")
            
            # Identify lessons
            all_lesson_links = []
            
            # Containers
            content_containers = soup.select(".main-content, #syllabus, .syllabus, .product-outline, .category-list, .panel__body, .panel-collapse, .course-curriculum, .category-outline")
            
            # Filter sidebars
            valid_containers = []
            for container in content_containers:
                is_sidebar = False
                parent = container
                while parent:
                    if parent.name in ['aside'] or (parent.get('class') and any(c in ['sidebar', 'main-sidebar'] for c in parent.get('class'))):
                        is_sidebar = True
                        break
                    parent = parent.parent
                if not is_sidebar:
                    valid_containers.append(container)

            if valid_containers:
                for container in valid_containers:
                    # Look for lesson links
                    # Added 'a.card' for some themes
                    for a in container.select("a.category-post, a.product-outline-post, .syllabus__item a, a[href*='/posts/'], a.card, .post-item a, .panel__body a, .panel-collapse a, .list-group-item a"):
                         all_lesson_links.append(a)
            
            # Fallback: If no links found in specific containers, search everywhere (but avoid sidebars)
            if not all_lesson_links:
                if valid_containers:
                     print("     ⚠️ specific containers found empty. Falling back to global search.")
                
                # DEBUG: Print what we are seeing
                all_links = soup.find_all("a", href=True)
                print(f"     🔍 GLOBAL DEBUG: Found {len(all_links)} links on page.")
                if len(all_links) > 0:
                    print(f"     🔍 SAMPLE LINKS: {[a['href'] for a in all_links[:5]]}")

                for a in all_links:
                    if "/posts/" in a['href']:
                        # Skip if inside an aside/sidebar
                        if not a.find_parent(['aside', 'nav']) and not a.find_parent(class_=['sidebar', 'main-sidebar']):
                            all_lesson_links.append(a)

            # Local deduplication & Filtering
            lesson_items = []
            seen_hrefs = set()
            
            def filter_lessons(raw_links):
                items = []
                for link in raw_links:
                    href = link.get("href")
                    # Must contain /posts/ and NOT be a category link pretending to be a post
                    if href and "/posts/" in href and href not in seen_hrefs:
                         # BUG FIX: Some URLs are /categories/ID/posts/ID, so we CANNOT exclude /categories/ blindly.
                         # Instead, we just ensure it has /posts/ (which is checked above).
                         # Only exclude if it is PURELY a category link (no 'posts') - but the outer if handles that.
                         items.append(link)
                         seen_hrefs.add(href)
                return items

            # Process links found in specific containers
            lesson_items = filter_lessons(all_lesson_links)
            
            # FAILSAFE: If specific containers yielded NO VALID LESSONS, try Global Search
            if not lesson_items:
                print("     ⚠️ Specific containers yielded no valid lessons. Attemping GLOBAL SEARCH...")
                
                all_links = soup.find_all("a", href=True)
                global_candidates = []
                for a in all_links:
                    href = a['href']
                    if "/posts/" in href:
                         is_sidebar = False
                         # Quick parent check for sidebar
                         if a.find_parent(['aside', 'nav']) or a.find_parent(class_=lambda c: c and ('sidebar' in c or 'menu' in c)):
                             is_sidebar = True
                         
                         if not is_sidebar:
                             global_candidates.append(a)
                
                # Filter these candidates
                lesson_items = filter_lessons(global_candidates)
                print(f"     🔍 Global Search Result: Found {len(lesson_items)} lessons.")

            if not lesson_items:
                print("     ⚠️ No lessons found on this page (Global Search Empty).")
                # Debug HTML dump
                try:
                    with open(".storage/debug_failed_page.html", "w", encoding="utf-8") as f:
                        f.write(driver.page_source)
                    print("     🔴 Saved page source to .storage/debug_failed_page.html")
                except: pass
                break
                
            print(f"     Found {len(lesson_items)} unique lessons. Extracting...")

            for link in lesson_items:
                if limit and limit > 0 and (len(videos) >= limit):
                     return videos

                href = link.get("href")
                full_link = self.base_url + href if href.startswith("/") else href
                
                # --- Sub-Section Detection ---
                # Look for H2/H3 headings that define a sub-section within this category
                parent_item = link.find_parent(class_=lambda c: c and any(x in str(c) for x in ["syllabus__item", "post-item", "category-item", "card"]))
                
                detected_subsection = None
                search_node = parent_item if parent_item else link
                
                # Find previous heading
                prev_heading = search_node.find_previous(["h2", "h3", "h4", "h5", "div"], class_=lambda c: c and any(x in str(c) for x in ["category-title", "section-title"]))
                if not prev_heading:
                     prev_heading = search_node.find_previous(["h2", "h3"]) # Fallback to generic headers
                
                if prev_heading:
                    st_cand = prev_heading.get_text(strip=True)
                    # Validate
                    if (st_cand and len(st_cand) > 2 and len(st_cand) < 100 and 
                        st_cand != course_title and st_cand != category_name and 
                        "videos" not in st_cand.lower()): # Avoid "21 videos"
                        detected_subsection = st_cand

                if detected_subsection:
                    # Clean subsection name
                    detected_subsection = re.sub(r'\(\d+.*?\)', '', detected_subsection).strip()
                    current_subsection = detected_subsection
                
                # --- Title Extraction ---
                # Priority 1: Specific Title Classes
                title_candidate = link.select_one(".product-outline-post__title, p.syllabus__title, .post-title, .syllabus__item-title, .card__title")
                raw_text = ""
                
                if title_candidate: 
                    raw_text = title_candidate.get_text(separator=" ", strip=True)
                
                # Priority 2: Link Text (but filtered)
                if not raw_text or raw_text.lower() in ["start", "resume", "view", "watch"]:
                    # Inspect link text logic: exclude children that might be buttons
                    # Or just get text.
                    t = link.get_text(separator=" ", strip=True)
                    if t.lower() not in ["start", "resume", "view", "watch"]:
                        raw_text = t
                
                # Cleanup Title
                clean_title = raw_text.replace("\n", " ").replace("\r", " ")
                clean_title = re.sub(r'\s+', ' ', clean_title).strip()
                
                # Final check if title is still generic
                if not clean_title or clean_title.lower() in ["start", "resume"]:
                    continue # Skip if we can't find a real title? Or use "Untitled Lesson"?
                
                # --- Metadata Extraction ---
                syllabus_text = ""
                syllabus_links = []
                parent_media = link.find_parent(class_="media-body") or link.find_next_sibling(class_="media-body") or link.find_parent(class_="card")
                if parent_media:
                    text_node = parent_media.select_one(".syllabus__text, .product-outline-post__text, .card__body")
                    if text_node:
                        syllabus_text = text_node.get_text(separator="\n", strip=True)
                        for a in text_node.find_all("a", href=True):
                            syllabus_links.append({"text": a.get_text(strip=True) or "Link", "url": a['href']})

                try:
                    # Fetch Lesson Page
                    lesson_data = self._extract_lesson_content(driver, full_link, default_title=clean_title)
                    if lesson_data:
                        # Use URL as key if available (video), otherwise use course_url
                        v_url = lesson_data.get('url')
                        dedup_key = v_url if v_url else full_link
                        
                        if dedup_key in self.found_urls:
                            print(f"     ⏭️ Skipping Duplicate: {lesson_data['title']}")
                            continue
                            
                        self.found_urls.add(dedup_key)
                        lesson_data['course_title'] = course_title
                        lesson_data['category'] = category_name # Primary Section (Module)
                        lesson_data['subsection'] = current_subsection # Secondary Section if found
                        
                        # Set 'section' for backward compatibility
                        if current_subsection and current_subsection != "General":
                             lesson_data['section'] = current_subsection
                        else:
                             lesson_data['section'] = category_name

                        # Merge syllabus
                        if syllabus_text:
                            lesson_data['description'] = (syllabus_text + "\n\n" + lesson_data.get('description', '')).strip()
                        if syllabus_links:
                            lesson_data['links'] = syllabus_links + lesson_data.get('links', [])
                        
                        videos.append(lesson_data)
                        print(f"     ✅ Found: {lesson_data['title']} {'(Video)' if v_url else '(Text)'}")
                        if callback: callback(lesson_data)
                    
                    driver.get(current_page_url)
                    time.sleep(1)
                except Exception as e:
                    print(f"     ❌ Error processing lesson {clean_title}: {e}")
                    import traceback
                    traceback.print_exc()
                    driver.get(current_page_url) 

            # Pagination Logic
            next_url = None
            # Standard Platform Pagination
            next_container = soup.select_one(".pagination, .pagination__next, a[rel='next']")
            if next_container:
                if next_container.name == 'a':
                    next_url = next_container.get('href')
                else:
                    n_link = next_container.select_one("a[rel='next'], a[aria-label='Next'], a:contains('Next')")
                    if n_link: next_url = n_link.get('href')
            
            # Fallback to fuzzy text match
            if not next_url:
                for a in soup.find_all("a", href=True):
                    text = a.get_text(strip=True).lower()
                    if text in ["next", "next page", "next >", ">"]:
                        next_url = a["href"]
                        break
            
            if next_url:
                from urllib.parse import urljoin
                next_url = urljoin(current_page_url, next_url)
                if next_url != current_page_url:
                    print(f"     ✅ Found next page: {next_url}")
                    page_number += 1
                    current_page_url = next_url
                else:
                    break
            else:
                break
                
        return videos

    def _extract_lesson_content(self, driver, lesson_url, default_title=None):
        driver.get(lesson_url)
        time.sleep(1.5) 
        
        soup = BeautifulSoup(driver.page_source, "html.parser")
        
        final_title = "Unknown Title"
        if default_title and len(default_title) > 2 and default_title.lower() != "start":
            final_title = default_title
        else:
            page_title = driver.title.strip()
            clean_title = page_title
            for suffix in [" | Platform", " - Platform", " | Service"]:
                clean_title = clean_title.replace(suffix, "")
            
            if len(clean_title) > 3:
                 final_title = clean_title
            else:
                 title_tag = soup.select_one("h1.post-title") or soup.select_one("span.post-title")
                 if title_tag:
                     # Remove icons/SVGs before extracting text
                     for icon in title_tag.select("svg, i, .icon, span[class*='icon']"):
                         icon.decompose()
                     final_title = title_tag.get_text(strip=True)
            
            # Clean Garbage (Regex)
            # Remove "video lesson icon...", "Created with Sketch", etc.
            final_title = re.sub(r'(?i)video lesson icon.*?Sketch\.?', '', final_title).strip()
            final_title = re.sub(r'(?i)Instructions:.*', '', final_title).strip() 

        
        # Explicit Wait for Content
        # Often the title loads fast, but the body (.post-body) is lazy loaded
        try:
            WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".post-body, .user-content, #section-post_body"))
            )
        except:
            pass

        # Refresh Soup after potential wait
        soup = BeautifulSoup(driver.page_source, "html.parser")
        
        body_content = ""
        extracted_links = []
        
        # Priority Order: Specific body classes FIRST, then generic ones
        # We process them in order and STOP if we find substantial content in a high-priority container
        
        priority_selectors = [
            ".post-body", 
            ".user-content", 
            "#section-post_body", 
            "#post-body",
            ".product-outline-post__text", # Platform specific for some themes
            ".panel__body", # Generic - risky if it contains comments
            ".panel__block",
            ".media-body"
        ]
        
        selected_div = None
        
        # Try each selector
        for selector in priority_selectors:
            candidates = soup.select(selector)
            for div in candidates:
                # Check 1: Is this a Comments section?
                # Look for "Comments" header or ID
                if div.get("id") == "comments" or "comments" in (div.get("class") or []):
                    continue
                
                # Check 2: Does it contain a Comments header directly?
                # Sometimes comments are inside .panel__body
                # Heuristic: If it starts with "Comments", skip it
                text_preview = div.get_text(strip=True)[:50]
                if "Comments" in text_preview and len(div.get_text(strip=True)) > 500: 
                    # If it starts with Comments AND is long, it's likely the full comments section
                    continue
                
                # Check 3: Is it inside a sidebar?
                if div.find_parent("aside") or div.find_parent(class_="sidebar"):
                    continue

                # Check 4: Sidebar/Navigation Content Validation (NEW)
                # If text starts with "Complete" and "Great Job", it's likely navigation, not lesson body.
                text_preview_nav = div.get_text(separator="\n", strip=True)[:100].replace("\n", " ")
                if "Complete" in text_preview_nav and ("Great Job" in text_preview_nav or "Next Lesson" in text_preview_nav):
                    # Only skip if we have other options? No, this is definitely bad.
                    # But be careful not to skip real content if it just happens to have these words.
                    # The navigation block usually STARTS with this.
                    continue

                # If we are here, this candidate is promising
                # Check length
                text_len = len(div.get_text(strip=True))
                if text_len > 10: # Arbitrary threshold for "real content"
                    selected_div = div
                    break
            
            if selected_div:
                break
        
        # If still nothing, try the old generic fallback but filter carefully
        if not selected_div:
             # ... (existing fallback logic if needed, but the priority list covers most)
             pass

        if selected_div:
             div = selected_div
             # 1. Collect External/Sidebar Links FIRST
             extracted_links = []
             for a in div.find_all("a", href=True):
                 link_text = a.get_text(strip=True) or "Link"
                 link_url = a['href']
                 
                 if link_url.startswith("http") and link_url not in seen_links:
                     # Heuristic: Internal course links shouldn't be in the global "Links" section
                     if "/products/" in link_url and "/categories" in link_url:
                         continue
                     extracted_links.append({"text": link_text, "url": link_url})
                     seen_links.add(link_url)

             # 2. IN-TEXT LINK PRESERVATION: Convert <a> to Markdown [text](url)
             # Note: We iterate a second time to replace them in the DOM
             for a in div.find_all("a", href=True):
                 t = a.get_text(strip=True)
                 u = a['href']
                 if u.startswith("http") and t:
                     # Only convert if it's likely a real content link
                     if "/products/" not in u or "/posts/" in u:
                         a.replace_with(f"[{t}]({u})")

             # 3. Capture text
             body_content = div.get_text(separator="\n", strip=True)
        
        page_source = driver.page_source
        wistia_id = None
        iframe_match = re.search(r'fast\.wistia\.(?:com|net)/embed/iframe/([a-zA-Z0-9]+)', page_source)
        if iframe_match:
            wistia_id = iframe_match.group(1)
        
        if not wistia_id:
            script_match = re.search(r'async src="https://fast\.wistia\.com/embed/medias/([a-zA-Z0-9]+)\.jsonp"', page_source)
            if script_match:
                wistia_id = script_match.group(1)
        
        # Return Lesson Data regardless of video
        return {
            "title": final_title,
            "url": f"https://fast.wistia.net/embed/iframe/{wistia_id}" if wistia_id else None,
            "course_url": lesson_url,
            "description": body_content,
            "links": extracted_links,
            "html": driver.page_source # Save HTML for archiving
        }
