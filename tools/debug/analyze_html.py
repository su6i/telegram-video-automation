from bs4 import BeautifulSoup
import sys

try:
    with open("debug_course_source.html", "r", encoding="utf-8") as f:
        soup = BeautifulSoup(f, "html.parser")

    # Find last known video
    print("Searching for 'Capcut'...")
    last_vid = soup.find(string=lambda t: "Capcut" in t if t else False)
    if not last_vid:
        print("Searching for 'DaVinci'...")
        last_vid = soup.find(string=lambda t: "DaVinci" in t if t else False)
    
    if last_vid:
        print(f"Found Node: {last_vid}")
        parent = last_vid.find_parent("a") or last_vid.find_parent("div")
        if parent:
            print(f"Parent Class: {parent.get('class')}")
            # Identify container
            container = parent.find_parent("div", class_="syllabus") or parent.find_parent("div", class_="outline")
            if container:
                print("Found container.")
                # Look for pagination after container
                nxt = container.find_next_sibling()
                if nxt:
                    print(f"Next Sibling Tag: {nxt.name} Class: {nxt.get('class')}")
                    print(nxt.prettify()[:500])
                else:
                    print("No next sibling for container.")
            else:
                print("Container not identified. Printing parent's next siblings:")
                for s in parent.next_siblings:
                    if s.name:
                        print(f"Sibling: {s.name} Class: {s.get('class')}")
                        print(s.prettify()[:200])
                        break
    else:
        print("Target text not found.")

    # Explicitly check for pagination classes
    print("\n--- Pagination Check ---")
    pags = soup.select(".pagination, .pages, .nav-links")
    for p in pags:
        print(f"Pagination Widget: {p}")

    # Check for 'categories' in links
    print("\n--- Category Links Check ---")
    for a in soup.find_all("a", href=True):
        if "/categories/" in a['href']:
            print(f"Category: {a.get_text(strip=True)} -> {a['href']}")

except Exception as e:
    print(e)
