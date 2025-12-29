
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
meta_005 = {"course": "AI Creator Course", "section": "Intro to AI", "index": "005", "line_title": "ChatGPT Overview", "title": "ChatGPT Overview"}
extra_005 = {
    "links": [{"text": "chat.openai.com", "url": "https://chat.openai.com/"}],
    "description": "ChatGPT Overview\n12/25 Update! Personalization settings..."
}

meta_006 = {"course": "AI Creator Course", "section": "Intro to AI", "index": "006", "line_title": "Video 6", "title": "Video 6"}
extra_006 = {
    "links": [],
    "description": "Cool Video Info\nComments\n123\nPost Comment\nUser: Nice video!\nREPLY"
}

print("--- VIDEO 005 CAPTION ---")
print(format_caption(meta_005, extra_005))
print("\n--- VIDEO 006 CAPTION (Initially Dirty) ---")
print(format_caption(meta_006, extra_006))
