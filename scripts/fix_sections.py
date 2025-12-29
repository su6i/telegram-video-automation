#!/usr/bin/env python3
"""
Fix manifest sections by grouping consecutive videos with similar patterns
"""

import re
from collections import Counter

manifest_path = '.storage/downloaded_video.txt'

# Read manifest
with open(manifest_path, 'r') as f:
    lines = f.readlines()

# Parse videos and analyze patterns
videos = []
for line in lines:
    if line.strip() and line[0].isdigit() and '|' in line:
        parts = [p.strip() for p in line.split('|')]
        if len(parts) >= 5:
            videos.append({
                'line': line,
                'index': parts[0],
                'title': parts[1][:30],
                'course': parts[3],
                'section': parts[4],
                'full_line': '|'.join(parts)
            })

# Detect patterns within each course
course_groups = {}
for v in videos:
    course = v['course']
    if course not in course_groups:
        course_groups[course] = []
    course_groups[course].append(v)

# For each course, detect the REAL sections
# Strategy: Section changes when we see a major pattern shift in titles or explicit section changes
fixed_videos = []

for course, course_vids in course_groups.items():
    print(f"\n📚 Analyzing {course}:")
    
    current_real_section = "General"
    
    for i, vid in enumerate(course_vids):
        # Try to detect section from title patterns
        title_lower = vid['title'].lower()
        
        # Look for section indicators in titles (like "CapCut Desktop", "Premiere Pro", etc)
        section_indicators = []
        
        # Check if title contains tool names or platform names
        tools = ['capcutdesktop', 'capcutmobile', 'adobepremierepro', 'davinciresolve', 'finalcutpro']
        for tool in tools:
            if tool in title_lower.replace(' ', '').replace('-', ''):
                section_indicators.append(tool.replace('capcutdesktop', 'CapCut Desktop')
                                                  .replace('capcutmobile', 'CapCut Mobile')
                                                  .replace('adobepremierepro', 'Adobe Premiere Pro')
                                                  .replace('davinciresolve', 'DaVinci Resolve')
                                                  .replace('finalcutpro', 'Final Cut Pro'))
        
        if section_indicators:
            current_real_section = section_indicators[0]
        
        # Update the video with corrected section
        vid['corrected_section'] = current_real_section
        fixed_videos.append(vid)
        
        print(f"  {vid['index']}: {vid['title']:30} -> {current_real_section}")

# Write back manifest with corrected sections
with open(manifest_path, 'w') as f:
    f.write("# Index | Title | URL | Course | Section | Status\n")
    f.write("# To skip a video, delete the line or put a '#' at the start\n")
    
    current_course = None
    current_section = None
    
    for v in fixed_videos:
        # Write course header if changed
        if v['course'] != current_course:
            f.write(f"\n# === {v['course']} (X videos) ===\n")
            current_course = v['course']
            current_section = None
        
        # Write section header if changed
        if v['corrected_section'] != current_section:
            f.write(f"\n## --- {v['corrected_section']} ---\n")
            current_section = v['corrected_section']
        
        # Write video line
        f.write(f"{v['full_line']}\n")

print("\n✅ Fixed! Sections are now properly grouped.")
