
import re
import json

def format_caption(meta, extra):
    header_parts = [f"**{meta['course']}**"]
    if meta['section'] and meta['section'] != "General":
        header_parts.append(f"**{meta['section']}**")
    
    final_title = meta['line_title'] if meta['line_title'] else meta['title']
    header_parts.append(f"**{meta['index']} - {final_title}**")
    
    caption = "\n".join(header_parts) + "\n\n"
    
    if extra:
        if extra.get('links'):
            caption += "🔗 **Links:**\n"
            for link in extra['links']:
                caption += f"• [{link['text']}]({link['url']})\n"
            caption += "\n"
        
        if extra.get('description'):
            desc = extra['description']
            desc = re.split(r'(?i)Comments\s*\n\s*\d+', desc)[0]
            desc = re.split(r'(?i)Post Comment', desc)[0]
            desc = re.split(r'(?i)\n\d+\s+Comments', desc)[0]
            desc = re.split(r'(?m)^\d+ (minutes|hours|days|weeks|months) ago', desc)[0]
            desc = re.split(r'(?m)^REPLY\s*\n', desc)[0]
            desc = desc.strip()
            desc = re.sub(r'(^|\n)(\d{1,2}/\d{1,2} Update!.*?)(?=\n|$)', r'\1\n**\2**', desc)
            desc = re.sub(r'(^|\n)(Update!.*?)(?=\n|$)', r'\1\n**\2**', desc)
            
            if desc:
                caption += f"📝 **Info:**\n{desc}"
    return caption

# Mock Data
meta_005 = {"course": "Example Masterclass", "section": "Getting Started", "index": "005", "line_title": "Overview Lesson", "title": "Overview Lesson"}
extra_005 = {
    "links": [{"text": "example.com", "url": "https://example.com/"}],
    "description": "Overview Lesson\n12/25 Update! Important notes..."
}

meta_006 = {"course": "Example Masterclass", "section": "Getting Started", "index": "006", "line_title": "Deep Dive", "title": "Deep Dive"}
extra_006 = {
    "links": [],
    "description": "Technical details\nComments\n123\nPost Comment\nUser: Great info!\nREPLY"
}

print("--- VIDEO 005 CAPTION ---")
print(format_caption(meta_005, extra_005))
print("\n--- VIDEO 006 CAPTION (Initially Dirty) ---")
print(format_caption(meta_006, extra_006))
