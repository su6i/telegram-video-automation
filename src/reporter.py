def print_detailed_statistics(collected_lessons):
    """
    Prints a pretty ASCII table of the scan results.
    Breakdown: Course > Section > Sub-section > Count
    """
    if not collected_lessons: return

    print("\n" + "╔" + "═"*78 + "╗")
    print(f"║ {'SCAN STATISTICS':^76} ║")
    print("╠" + "═"*78 + "╣")
    
    # 1. Group Data
    stats = {} # {Course: {Section: {Subsection: count}}}
    
    for l in collected_lessons:
        c = l.get('course_title', 'Unknown')
        s = l.get('section', 'General')
        sub = l.get('subsection') or "(No Subsection)"
        
        if c not in stats: stats[c] = {}
        if s not in stats[c]: stats[c][s] = {}
        if sub not in stats[c][s]: stats[c][s][sub] = 0
        stats[c][s][sub] += 1
        
    # 2. Print Hierarchy
    total_videos = 0
    
    for course, sections in stats.items():
        c_count = sum(sum(subs.values()) for subs in sections.values())
        print(f"║ 📘 {course[:65]:<65} {c_count:>8} ║")
        print("║" + "-"*78 + "║")
        
        for section, subsections in sections.items():
            s_count = sum(subsections.values())
            print(f"║    📂 {section[:60]:<60} {s_count:>8} ║")
            
            for sub, count in subsections.items():
                if sub == "(No Subsection)": continue
                print(f"║       └── {sub[:55]:<55} {count:>8} ║")
            
        print("╠" + "═"*78 + "╣")
        total_videos += c_count

    print(f"║ {'TOTAL VIDEOS':<65} {total_videos:>8} ║")
    print("╚" + "═"*78 + "╝")
