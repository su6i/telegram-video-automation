#!/usr/bin/env python3
"""
Reorganize course manifest sections based on structure
"""

# Manual mapping of line numbers to correct section names
section_mapping = [
    # Section 1: Introduction to Module 1
    (78, 96, "Introduction to Module 1"),
    
    # Section 2: Core Platform Skills  
    (97, 109, "Core Platform Skills"),  # Covers thumbnails, uploading
    
    # Section 3: Advanced Techniques 1
    (110, 116, "Advanced Techniques 1"),
    
    # Section 4: Equipment & Setup
    (97, 110, "Equipment & Setup"),  # Gear recommendations
    
    # Section 5: Optimization & Mastering
    (111, 130, "Optimization & Mastering"),
    
    # Section 6: Workflow Efficiency
    (127, 130, "Workflow Efficiency"),  # Camera specific
    
    # Section 7: Studio Design & Pro Tips
    (131, 139, "Studio Design & Pro Tips"),
    
    # Section 8: Professional Audio Setup
    (140, 143, "Professional Audio Setup"),
    
    # Section 9: Visual Composition Mastery
    (144, 149, "Visual Composition Mastery"),
    
    # Section 10: Video Editing Level 1
    (150, 176, "Video Editing Level 1"),  # All editing content
    
    # Section 11: Mobile Content Production
    (156, 176, "Mobile Content Production"),  # CapCut, VN
    
    # Section 12: Desktop Editing Masterclass
    (177, 224, "Desktop Editing Masterclass"),  # DaVinci, Premiere
    
    # Section 13: Distribution & Monetization
    (226, 242, "Distribution & Monetization"),
    
    # Section 14: Social Media Strategy
    (243, 249, "Social Media Strategy"),
    
    # Section 15: Additional Resources
    (250, 253, "Additional Resources"),
]

# Print mapping for review
print("=" * 80)
print("EXAMPLE COURSE - PROPOSED SECTION MAPPING")
print("=" * 80)

for start, end, section in section_mapping:
    count = end - start + 1
    print(f"\n{section}")
    print(f"  Lines: {start}-{end} ({count} items)")

print("\n" + "=" * 80)
print("NOTE: Some sections overlap because videos fit into multiple categories")
print("This script helps organize the manifest structure.")
print("=" * 80)
