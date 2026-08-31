#!/usr/bin/env python3
"""
Fix manifest by removing duplicate section headers
"""

import re

manifest_path = '.storage/downloaded_video.txt'

with open(manifest_path, 'r') as f:
    lines = f.readlines()

fixed_lines = []
prev_section = None
current_section = None

for line in lines:
    # Check if it's a section header
    if line.startswith('## ---'):
        current_section = line.strip()
        # Only write section header if it's different from previous OR it's the first video in a course
        if current_section != prev_section:
            # Check if next line is a video (not another header or comment)
            idx = lines.index(line) if line in lines else -1
            if idx != -1 and idx + 1 < len(lines):
                next_line = lines[idx + 1]
                # Only keep section header if next line is a video line (starts with digits)
                if next_line.strip() and (next_line[0].isdigit() or next_line.startswith('#')):
                    fixed_lines.append(line)
                    prev_section = current_section
                # Skip duplicate section headers
            else:
                fixed_lines.append(line)
                prev_section = current_section
    else:
        fixed_lines.append(line)

# Write back
with open(manifest_path, 'w') as f:
    f.writelines(fixed_lines)

print("✅ Manifest fixed!")
print(f"   Removed duplicate section headers")
print(f"   Total lines: {len(fixed_lines)}")
