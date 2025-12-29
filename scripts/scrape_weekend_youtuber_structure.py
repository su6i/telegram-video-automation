#!/usr/bin/env python3
"""
Scrape Weekend Youtuber course structure from contentcreator.com
Extracts all sections, lessons, and lesson types
"""

import json
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import time

def scrape_course_structure(url, course_name):
    """
    Scrape course structure from contentcreator.com
    Returns dictionary with sections and their lessons
    """
    
    # Setup Chrome driver
    options = webdriver.ChromeOptions()
    options.add_argument('--start-maximized')
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_argument('user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36')
    
    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=options
    )
    
    try:
        print(f"Loading {course_name} page...")
        driver.get(url)
        
        # Wait for page to load
        wait = WebDriverWait(driver, 10)
        wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, ".curriculum-section")))
        
        time.sleep(3)  # Extra wait for dynamic content
        
        course_structure = {}
        
        # Get all sections
        sections = driver.find_elements(By.CSS_SELECTOR, ".curriculum-section")
        print(f"Found {len(sections)} sections")
        
        for idx, section in enumerate(sections):
            try:
                # Get section title
                section_title_elem = section.find_element(By.CSS_SELECTOR, ".section-title, h3, .curriculum-section-title")
                section_title = section_title_elem.text.strip()
                
                if not section_title:
                    section_title = f"Section {idx + 1}"
                
                print(f"\n📂 {section_title}")
                
                # Get all lessons in this section
                lessons = section.find_elements(By.CSS_SELECTOR, ".lesson-item, .curriculum-item, li")
                
                section_lessons = []
                
                for lesson in lessons:
                    try:
                        lesson_text = lesson.text.strip()
                        
                        if not lesson_text or len(lesson_text) < 3:
                            continue
                        
                        # Check if it's a video or text/exercise
                        has_video = "play" in lesson.get_attribute("class").lower() or \
                                   lesson.find_elements(By.CSS_SELECTOR, ".video-icon, [class*='play']")
                        
                        lesson_type = "VIDEO" if has_video else "TEXT/RESOURCE"
                        
                        section_lessons.append({
                            "title": lesson_text,
                            "type": lesson_type
                        })
                        
                        print(f"  - [{lesson_type}] {lesson_text[:80]}")
                        
                    except Exception as e:
                        continue
                
                if section_lessons:
                    course_structure[section_title] = section_lessons
            
            except Exception as e:
                print(f"  Error parsing section: {e}")
                continue
        
        return course_structure
    
    finally:
        driver.quit()

def main():
    url = "https://www.contentcreator.com/products/weekend-youtuber/categories"
    
    print("=" * 80)
    print("SCRAPING: Weekend Youtuber Course Structure")
    print("=" * 80)
    
    structure = scrape_course_structure(url, "Weekend Youtuber")
    
    # Save to JSON
    output_file = "/Users/su6i/@-github/telegram-video-automation/.storage/weekend_youtuber_structure.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(structure, f, ensure_ascii=False, indent=2)
    
    print(f"\n\n✅ Structure saved to {output_file}")
    print(f"\nTotal Sections: {len(structure)}")
    total_lessons = sum(len(v) for v in structure.values())
    print(f"Total Lessons: {total_lessons}")
    
    # Print summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    for section, lessons in structure.items():
        videos = [l for l in lessons if l["type"] == "VIDEO"]
        resources = [l for l in lessons if l["type"] != "VIDEO"]
        print(f"\n{section}")
        print(f"  Videos: {len(videos)}")
        print(f"  Resources/Exercises: {len(resources)}")

if __name__ == "__main__":
    main()
