import os
import json
import re
import urllib.parse
import shutil
from pathlib import Path
from bs4 import BeautifulSoup

STORAGE_DIR = ".storage"
ARCHIVE_DIR = os.path.join(STORAGE_DIR, "course_archive")
VIEWER_DIR = os.path.join(STORAGE_DIR, "viewer")
MANIFEST_FILE = os.path.join(STORAGE_DIR, "downloaded_video.txt")
SCRAPED_CONTENT_FILE = os.path.join(STORAGE_DIR, "scraped_content.json")
DOWNLOADS_DIR = "downloads"

def _sanitize_path(name):
    if not name: return ""
    name = re.sub(r'^\d+_', '', name)
    name = name.replace("video_lesson_icondefault_Created_with_Sketch_", "")
    sanitized = re.sub(r'[^\w\s\-]', '', name)
    sanitized = re.sub(r'\s+', '_', sanitized)
    sanitized = re.sub(r'-+', '-', sanitized)
    return sanitized.lower().strip('_')

def get_html_map():
    html_map = {}
    if not os.path.exists(ARCHIVE_DIR): return html_map
    for root, dirs, files in os.walk(ARCHIVE_DIR):
        f_name = None
        for f in ["index.html", "page_source.html", "content.txt"]:
            if f in files:
                f_name = f
                if f in ["index.html", "page_source.html"]: break
        if f_name:
            path = os.path.abspath(os.path.join(root, f_name))
            p, gp = os.path.basename(root), os.path.basename(os.path.dirname(root))
            keys = [p.lower(), _sanitize_path(p), f"{gp.lower()}/{p.lower()}", _sanitize_path(f"{gp}/{p}")]
            for k in keys:
                if k: html_map[k] = path
    return html_map

def get_url_to_path_map():
    url_to_local = {}
    html_lookup = get_html_map()
    scraped_map = {}
    if os.path.exists(SCRAPED_CONTENT_FILE):
        try:
            with open(SCRAPED_CONTENT_FILE, "r") as f:
                data = json.load(f)
                for w_url, meta in data.items():
                    if "course_url" in meta: scraped_map[w_url] = meta["course_url"]
        except: pass

    if os.path.exists(MANIFEST_FILE):
        with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
            for line in f:
                if "|" in line and not line.startswith("#"):
                    parts = [p.strip() for p in line.split("|")]
                    m_url = parts[-1]
                    raw_name = parts[1] if parts[0].isdigit() and len(parts) >= 3 else parts[0]
                    slug = _sanitize_path(raw_name)
                    local_path = html_lookup.get(slug)
                    if not local_path:
                        for k, v in html_lookup.items():
                            if slug in k or k in slug: local_path = v; break
                    if local_path:
                        url_to_local[m_url] = local_path
                        url_to_local[urllib.parse.urlparse(m_url).path] = local_path
                        if m_url in scraped_map:
                            k_url = scraped_map[m_url]
                            url_to_local[k_url] = local_path
                            url_to_local[urllib.parse.urlparse(k_url).path] = local_path
    return url_to_local

def parse_manifest():
    if not os.path.exists(MANIFEST_FILE): return {}
    courses, cur_c, cur_s = {}, "Other", "General"
    with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.startswith("# ==="): cur_c, cur_s = line.strip("# = ").strip(), "General"
            elif line.startswith("## ---"): cur_s = line.strip("# - ").strip()
            elif "|" in line and not line.startswith("#"):
                p = [x.strip() for x in line.split("|")]
                if len(p) >= 2:
                    raw = p[1] if p[0].isdigit() and len(p) >= 3 else p[0]
                    m_name = f"{p[0]}_{p[1]}" if p[0].isdigit() and len(p) >= 3 else p[0]
                    if cur_c not in courses: courses[cur_c] = {}
                    if cur_s not in courses[cur_c]: courses[cur_c][cur_s] = []
                    courses[cur_c][cur_s].append({"title": re.sub(r'^\d+_', '', raw), "match_name": m_name, "id_num": p[0] if p[0].isdigit() else ""})
    return courses

def generate_portal():
    print("🏗️ Updating Portal with Absolute-style links...")
    courses, html_map = parse_manifest(), get_html_map()
    parts = []
    css = "<style>body{font-family:'Inter',sans-serif;background:#0f172a;color:white;padding:40px;margin:0}.container{max-width:1400px;margin:0 auto}h1{color:#38bdf8;border-bottom:2px solid #1e293b;padding-bottom:20px;text-align:center;margin-bottom:40px;font-weight:800}.courses-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(450px,1fr));gap:40px}.course-card{background:#1e293b;border-radius:20px;padding:30px;border:1px solid #334155}.course-card h2{color:#38bdf8;margin-top:0;font-size:1.8rem;text-transform:uppercase;border-bottom:1px solid #334155;padding-bottom:15px;margin-bottom:25px}.section-block{margin-bottom:30px;background:rgba(15,23,42,.4);border-radius:12px;padding:15px;border:1px solid rgba(56,189,248,.1)}.section-header{font-size:.85rem;color:#38bdf8;text-transform:uppercase;font-weight:800;margin-bottom:12px;display:flex;align-items:center}.section-header::after{content:'';flex:1;height:1px;background:#334155;margin-left:15px}.lesson-list{list-style:none;padding:0;margin:0}.lesson-list li{margin-bottom:8px}.lesson-list li a{color:#cbd5e1;text-decoration:none;padding:10px 15px;display:block;background:#0f172a;border-radius:8px;font-size:0.95rem;transition:all 0.2s}.lesson-list li a:hover{background:#1e293b;color:#38bdf8;transform:translateX(5px)}.lesson-list li.missing a{opacity:0.4;cursor:not-allowed;color:#64748b}</style>"
    for cn, sections in courses.items():
        sh = ""
        for sn, lessons in sections.items():
            li = ""
            for l in lessons:
                slug = _sanitize_path(l["match_name"])
                trg = html_map.get(slug)
                if not trg:
                    for k, v in html_map.items():
                        if slug in k or k in slug: trg = v; break
                if trg:
                    root_rel = "/" + os.path.relpath(trg, os.getcwd())
                    safe_url = urllib.parse.quote(root_rel, safe='/')
                    li += f'<li><a href="{safe_url}">{l["title"]}</a></li>'
                else: li += f'<li class="missing"><a href="#">{l["title"]} (Not Archived)</a></li>'
            if li: sh += f'<div class="section-block"><div class="section-header">{sn}</div><ul class="lesson-list">{li}</ul></div>'
        if sh: parts.append(f'<div class="course-card"><h2>{cn}</h2>{sh}</div>')
    os.makedirs(VIEWER_DIR, exist_ok=True)
    with open(os.path.join(VIEWER_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(f"<!DOCTYPE html><html><head><meta charset='UTF-8'><title>Local Course Viewer</title>{css}</head><body><div class='container'><h1>📚 My Offline Knowledge Base</h1><div class='courses-grid'>{''.join(parts)}</div></div></body></html>")
    print("✅ Portal updated.")

def patch_all_lessons():
    print("🔧 Restoring Multi-Drive Playback (Ghost File Purge)...")
    v_map = {}
    srch = [DOWNLOADS_DIR]
    if os.path.exists(mp := os.path.join(STORAGE_DIR, "media_paths.json")):
        try:
            with open(mp, "r") as f: srch.extend(json.load(f).get("paths", []))
        except: pass
    
    for s in srch:
        if not os.path.exists(s): continue
        for r, ds, fs in os.walk(s):
            for f in fs:
                if f.startswith("._") or f.startswith(".DS_Store"): continue
                if f.lower().endswith((".mp4", ".mkv", ".mov")): 
                    v_map[f.lower()] = os.path.abspath(os.path.join(r, f))

    link_map = get_url_to_path_map()
    v_proxy_abs = os.path.abspath(os.path.join(VIEWER_DIR, "v_proxy"))
    
    # CRITICAL: CLEAR PROXY DIR TO REMOVE STALE GHOST SYMLINKS
    if os.path.exists(v_proxy_abs):
        print(f"🧹 Clearing stale proxy links...")
        shutil.rmtree(v_proxy_abs)
    os.makedirs(v_proxy_abs, exist_ok=True)
    
    total = 0
    for r, ds, fs in os.walk(ARCHIVE_DIR):
        for h in ["index.html", "page_source.html"]:
            if h in fs:
                hp = os.path.join(r, h)
                try:
                    with open(hp, "r", encoding="utf-8") as f: soup = BeautifulSoup(f.read(), "html.parser")
                    
                    # 1. CLEAN SCRIPTS
                    for script in soup.find_all("script"):
                        src, text = script.get("src", "").lower(), (script.string.lower() if script.string else "")
                        kill = ["wistia", "facebook", "gtm.js", "analytics", "pixel", "tiktok", "axon", "snap.licdn"]
                        if any(p in src or p in text for p in kill): script.decompose()
                    
                    # 2. LINK REWRITING (ROOT-RELATIVE)
                    for a in soup.find_all("a", href=True):
                        href = a["href"].split("?")[0].split("#")[0]
                        repl = link_map.get(href) or link_map.get(urllib.parse.urlparse(href).path)
                        if not repl and href.startswith("/"):
                             for u, path in link_map.items():
                                 if u.endswith(href): repl = path; break
                        if repl:
                            root_rel = "/" + os.path.relpath(repl, os.getcwd())
                            a["href"] = urllib.parse.quote(root_rel, safe='/')

                    # 3. VIDEO PATCHING
                    old_box = soup.select_one(".local-media-box")
                    sel = [".kjb-video-responsive", "#wistia_60_wrapper", "[id^='wistia_']", "iframe[src*='wistia']", ".video-player", "[id^='wistia_child']", "video[src*='wistia']"]
                    cont = old_box or soup.select_one(", ".join(sel))
                    
                    if cont:
                        slug = _sanitize_path(os.path.basename(r))
                        mv = None
                        v_keys = sorted(v_map.keys(), key=len, reverse=True)
                        for vn in v_keys:
                            vn_slug = _sanitize_path(vn)
                            # Robust matching: either slug contains the other, or they share a major part
                            if slug and vn_slug and (slug in vn_slug or vn_slug in slug):
                                mv = v_map[vn]; break
                        
                        if mv and os.path.exists(mv):
                            v_ext = os.path.splitext(mv)[1].lower()
                            vsafe = f"{slug}{v_ext}" # ALWAYS LOWERCASE SYMLINK
                            pp = os.path.join(v_proxy_abs, vsafe)
                            
                            if not os.path.exists(pp): os.symlink(mv, pp)
                            
                            rv_root = "/" + os.path.relpath(pp, os.getcwd())
                            safe_rv = urllib.parse.quote(rv_root, safe='/')
                            v_type = "video/mp4" if v_ext != ".mov" else "video/quicktime"
                            
                            v_html = f'''
                            <div class="local-media-box" style="background:#000; padding:20px; border-radius:15px; margin:20px 0; border: 3px solid #38bdf8; position: relative; z-index: 1000;">
                                <video width="100%" controls preload="metadata" style="max-height: 85vh; border-radius:10px; display:block; background:#000;">
                                    <source src="{safe_rv}" type="{v_type}">
                                </video>
                                <div style="color:#38bdf8; margin-top:12px; text-align:center; font-size: 14px; font-weight:bold;">✅ LOCAL: {os.path.basename(mv)}</div>
                            </div>
                            <style>
                                .w-vulcan-v2, .w-chrome, .w-video-wrapper, .w-css-reset, iframe[src*='wistia'], .kjb-video-responsive {{ display: none !important; opacity: 0; visibility: hidden; }}
                                .local-media-box {{ display: block !important; opacity: 1 !important; visibility: visible !important; }}
                            </style>
                            '''
                            cont.replace_with(BeautifulSoup(v_html, "html.parser"))
                            total += 1
                    with open(hp, "w", encoding="utf-8") as f: f.write(str(soup))
                except Exception as e: print(f"   ⚠️ Error: {e}")
    print(f"✅ Reset and re-linked {total} pages. No ghost files remain.")

if __name__ == "__main__":
    generate_portal()
    patch_all_lessons()
