#!/usr/bin/env python3
"""
Reorganize Weekend Youtuber manifest sections based on course structure
"""

# Manual mapping of line numbers to correct section names
section_mapping = [
    # Section 1: Youtube Starter Secrets
    (78, 96, "Youtube Starter Secrets"),
    
    # Section 2: Essential Youtuber Skills  
    (97, 109, "Essential Youtuber Skills"),  # Covers thumbnails, uploading
    
    # Section 3: How to Have Charisma on Camera
    (110, 116, "How to Have Charisma on Camera"),
    
    # Section 4: Video Gear You DO & DON'T Need
    (97, 110, "Video Gear You DO & DON'T Need"),  # Gear recommendations
    
    # Section 5: Cinematic Settings & Smartphone Mastery
    (111, 130, "Cinematic Settings & Smartphone Mastery"),
    
    # Section 6: Mastering your PRO Camera
    (127, 130, "Mastering your PRO Camera"),  # Camera specific
    
    # Section 7: Pro Lighting & Studio Design
    (131, 139, "Pro Lighting & Studio Design"),
    
    # Section 8: Pro Youtuber Audio (on a budget)
    (140, 143, "Pro Youtuber Audio (on a budget)"),
    
    # Section 9: Cinematic B-Roll, Camera Movements, & Beautiful Composition
    (144, 149, "Cinematic B-Roll, Camera Movements, & Beautiful Composition"),
    
    # Section 10: Youtube Video Editing Masterclass
    (150, 176, "Youtube Video Editing Masterclass"),  # All editing content
    
    # Section 11: Cinematic SMARTPHONE Video Editing
    (156, 176, "Cinematic SMARTPHONE Video Editing"),  # CapCut, VN
    
    # Section 12: Computer Editing Masterclass
    (177, 224, "Computer Editing Masterclass"),  # DaVinci, Premiere
    
    # Section 13: Becoming a Full Time Youtuber (Monetization Blueprint)
    (226, 242, "Becoming a Full Time Youtuber (Monetization Blueprint)"),
    
    # Section 14: BONUS | Social Media Mastery
    (243, 249, "BONUS | Social Media Mastery"),
    
    # Section 15: DISCOUNTS | Saving you MONEY!
    (250, 253, "DISCOUNTS | Saving you MONEY!"),
]

# Print mapping for review
print("=" * 80)
print("WEEKEND YOUTUBER - PROPOSED SECTION MAPPING")
print("=" * 80)

for start, end, section in section_mapping:
    count = end - start + 1
    print(f"\n{section}")
    print(f"  Lines: {start}-{end} ({count} items)")

print("\n" + "=" * 80)
print("NOTE: Some sections overlap because videos fit into multiple categories")
print("You need to decide the correct structure.")
print("=" * 80)
