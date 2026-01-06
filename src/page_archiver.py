"""
Page archiver — save web pages locally with all assets (images, scripts, styles, etc.)
"""
import os
import json
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import mimetypes
from pathlib import Path


STORAGE_DIR = ".storage"
ARCHIVE_DIR = os.path.join(STORAGE_DIR, "page_archives")


def get_safe_filename(url):
    """Convert URL to safe filename."""
    parsed = urlparse(url)
    # Remove protocol and convert slashes to dashes
    clean = parsed.netloc.replace('.', '_').replace('-', '_')
    path = parsed.path.strip('/').replace('/', '_')
    if path:
        return f"{clean}_{path[:50]}"
    return clean


def archive_page(page_url, page_title=None):
    """
    Archive a complete web page with all assets.
    
    Args:
        page_url: URL to archive
        page_title: Optional friendly name for the page
    
    Returns:
        dict with archive info: {success, path, assets_count, images, links}
    """
    try:
        os.makedirs(ARCHIVE_DIR, exist_ok=True)
        
        # Create folder for this page
        safe_name = get_safe_filename(page_url)
        page_dir = os.path.join(ARCHIVE_DIR, safe_name)
        os.makedirs(page_dir, exist_ok=True)
        
        # Download main page
        print(f"📥 Downloading page: {page_url}")
        response = requests.get(page_url, timeout=30, headers={
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'
        })
        response.raise_for_status()
        
        # Parse HTML
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Track results
        results = {
            'url': page_url,
            'title': page_title or soup.title.string if soup.title else safe_name,
            'path': page_dir,
            'images': [],
            'links': [],
            'assets_count': 0
        }
        
        # Extract and download images
        print("  🖼️ Downloading images...")
        for img in soup.find_all('img'):
            img_url = img.get('src') or img.get('data-src')
            if not img_url:
                continue
            
            img_url = urljoin(page_url, img_url)
            try:
                img_response = requests.get(img_url, timeout=15)
                img_response.raise_for_status()
                
                # Get filename
                parsed_url = urlparse(img_url)
                img_name = os.path.basename(parsed_url.path)
                if not img_name or '.' not in img_name:
                    img_name = f"image_{len(results['images'])}.jpg"
                
                # Save image
                img_path = os.path.join(page_dir, 'images', img_name)
                os.makedirs(os.path.dirname(img_path), exist_ok=True)
                with open(img_path, 'wb') as f:
                    f.write(img_response.content)
                
                results['images'].append({
                    'original_url': img_url,
                    'local_path': f"images/{img_name}",
                    'alt_text': img.get('alt', '')
                })
                results['assets_count'] += 1
                
            except Exception as e:
                print(f"    ⚠️ Failed to download {img_url}: {e}")
        
        # Extract links and download attachments (PDF, ZIP, etc.)
        doc_extensions = ['.pdf', '.zip', '.docx', '.doc', '.xlsx', '.xls', '.mp3', '.pptx', '.txt']
        print("  📎 Downloading attachments...")
        for link in soup.find_all('a'):
            href = link.get('href')
            text = link.get_text(strip=True)
            if not href:
                continue
            
            full_url = urljoin(page_url, href)
            results['links'].append({
                'text': text,
                'url': full_url,
                'anchor': href
            })

            # Check if it's an attachment
            ext = os.path.splitext(urlparse(full_url).path)[1].lower()
            if ext in doc_extensions:
                try:
                    # Sanitize filename from URL or text
                    doc_name = os.path.basename(urlparse(full_url).path)
                    if not doc_name or len(doc_name) < 4:
                        doc_name = "".join(x for x in text if x.isalnum() or x in "._- ")[:40] + ext
                    
                    doc_path = os.path.join(page_dir, 'attachments', doc_name)
                    if os.path.exists(doc_path):
                        continue
                        
                    os.makedirs(os.path.dirname(doc_path), exist_ok=True)
                    print(f"    📩 Downloading attachment: {doc_name}")
                    doc_response = requests.get(full_url, timeout=30, headers={
                        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'
                    })
                    doc_response.raise_for_status()
                    with open(doc_path, 'wb') as f:
                        f.write(doc_response.content)
                    results['assets_count'] += 1
                except Exception as e:
                    print(f"    ⚠️ Failed to download attachment {full_url}: {e}")
        
        # Save original HTML
        html_path = os.path.join(page_dir, 'index.html')
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(response.text)
        results['assets_count'] += 1
        
        # Save metadata JSON
        meta_path = os.path.join(page_dir, 'metadata.json')
        with open(meta_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        
        print(f"✅ Page archived: {page_dir}")
        print(f"   📊 {results['assets_count']} assets, {len(results['images'])} images, {len(results['links'])} links")
        
        return {'success': True, **results}
        
    except Exception as e:
        print(f"❌ Failed to archive {page_url}: {e}")
        return {
            'success': False,
            'url': page_url,
            'error': str(e)
        }


def archive_course_pages(course_data):
    """
    Archive all pages for a course.
    
    Args:
        course_data: list of dicts with 'url', 'title' keys
    
    Returns:
        list of archive results
    """
    results = []
    for item in course_data:
        result = archive_page(item.get('url'), item.get('title'))
        results.append(result)
    
    return results


def list_archived_pages():
    """List all archived pages."""
    if not os.path.exists(ARCHIVE_DIR):
        return []
    
    archives = []
    for page_dir in os.listdir(ARCHIVE_DIR):
        meta_path = os.path.join(ARCHIVE_DIR, page_dir, 'metadata.json')
        if os.path.exists(meta_path):
            with open(meta_path, 'r', encoding='utf-8') as f:
                meta = json.load(f)
                archives.append(meta)
    
    return archives
