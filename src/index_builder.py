import html
import pathlib
import re

# The repo root has to be on sys.path before anything under src/ is imported
REPO = pathlib.Path(__file__).resolve().parents[1]

LIMIT = 3700           # visible chars per index post, in UTF-16 units (see
                       # utf16_len below); the hard cap is 4096.
ENT_LIMIT = 100        # Telegram's hard per-message entity cap (<a>, <b>, ...).
                       # Exceed it and the excess entities are silently
                       # dropped -- the text still renders, but the links
                       # past #100 go dead with no error and no truncation
                       # marker. 100 is Telegram's own cap, not a tuning
                       # knob: raising it drops links. (It used to also be the
                       # only value the index fit into -- 8 slots, where 95
                       # needed 9 posts. T-940 reclaimed 8 more slots, so that
                       # particular squeeze is gone; the cap is not.)

# sentinel for build_index_or_fail's available_slots: no ceiling on post count -- the per-post char/entity caps inside build_index still apply and still hard-fail.
UNBOUNDED = None

def utf16_len(s):
    """Telegram's char caps (LIMIT, 4096, CAPTION_LIMIT) count UTF-16 code
    units, not Python characters -- every emoji costs 2 there and 1 in
    Python's len(). Use this everywhere cost arithmetic touches text that
    might contain non-BMP characters."""
    return len(s.encode("utf-16-le")) // 2

def visible(s):
    return re.sub(r"<[^>]+>", "", s)

def resource_and_subtitle_ids(entry):
    """(resource_msg_id_or_None, subtitle_msg_id_or_None) for one lesson."""
    if not entry:
        return None, None
    parts = entry.get("pack_parts") or {}
    resource_id = parts[sorted(parts, key=int)[0]] if parts else entry.get("duplicate_note")
    return resource_id, entry.get("subtitle")

def read_manifest():
    course = section = None
    out = []
    text = (REPO / ".storage/downloaded_video.txt").read_text()
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("# === "):
            course = line[6:].rsplit("===", 1)[0].strip()
            section = None
            continue
        if line.startswith("## --- "):
            section = line[7:].rsplit("---", 1)[0].strip()
            continue
        m = re.match(r"^(\d{3})_(.*?)\s*\|", line)
        if m:
            out.append((course, section, m.group(1), m.group(2).strip()))
    return out

def build_index(entries, msg_of, internal, attach_state, include_resource=True, include_subtitle=True):
    posts, lines, vis, ent = [], [], 0, 0
    cur_course = cur_section = None

    def close():
        nonlocal lines, vis, ent
        if lines:
            posts.append("\n".join(lines))
            lines, vis, ent = [], 0, 0

    def add(h, v, e=0):
        nonlocal vis, ent
        lines.append(h)
        vis += v + 1
        ent += e

    for c, s, num, title in entries:
        new_course, new_section = c != cur_course, s != cur_section
        cost = utf16_len(num) + 4 + utf16_len(title)
        cost += (utf16_len(c) + 5) if new_course else 0
        cost += (utf16_len(s) + 5) if new_section else 0

        mid = msg_of.get(num)
        resource_id, subtitle_id = resource_and_subtitle_ids(attach_state.get(num))
        
        if not include_resource:
            resource_id = None
        if not include_subtitle:
            subtitle_id = None

        # Entities this line would add if it lands in the *current* post:
        # 1 for the lesson-title link (0 if there's no mid -- plain text
        # costs nothing), +1 per resource/subtitle link, +1 per course/
        # section header this line would trigger.
        cost_ent = (1 if mid else 0) + (1 if resource_id else 0) + (1 if subtitle_id else 0)
        # A new course forces a section header too, even when the section
        # name is unchanged across the boundary — charge both, or the
        # prediction under-counts by 1 and the post lands at 101 entities.
        cost_ent += (1 if new_course else 0) + (1 if (new_section or new_course) else 0)

        if lines and (vis + cost > LIMIT or ent + cost_ent > ENT_LIMIT):
            close()
            cur_course, cur_section = c, s
            # The (continued) header pair itself costs 2 entities (1 per
            # <b>) -- charge it through add()'s `e` argument, or the count
            # drifts and the split feeds back on itself.
            add(f"<b>🎓 {html.escape(c)} (continued)</b>", utf16_len(c) + 15, 1)
            add("", 0)
            add(f"<b>📁 {html.escape(s)}</b>", utf16_len(s) + 3, 1)
            new_course = new_section = False
        if new_course:
            if lines:
                add("", 0)
            cur_course, cur_section = c, None
            add(f"<b>🎓 {html.escape(c)}</b>", utf16_len(c) + 3, 1)
            new_section = True
        if new_section:
            cur_section = s
            add("", 0)
            add(f"<b>📁 {html.escape(s)}</b>", utf16_len(s) + 3, 1)
        extra = ""
        if resource_id:
            extra += f' <a href="https://t.me/c/{internal}/{resource_id}">📎</a>'
        if subtitle_id:
            extra += f' <a href="https://t.me/c/{internal}/{subtitle_id}">CC</a>'
        
        body = (f'{num}{extra} · <a href="https://t.me/c/{internal}/{mid}">{html.escape(title)}</a>'
                if mid else f"{num}{extra} · {html.escape(title)}")
        body_ent = (1 if mid else 0) + (1 if resource_id else 0) + (1 if subtitle_id else 0)
        add(body, utf16_len(num) + 3 + utf16_len(title) + utf16_len(visible(extra)), body_ent)
    close()
    return posts

def build_index_or_fail(entries, msg_of, internal, attach_state, available_slots, caller, *, include_resource=True, include_subtitle=True, extra_hint=None):
    posts = build_index(entries, msg_of, internal, attach_state, include_resource=include_resource, include_subtitle=include_subtitle)
    if available_slots is not None and len(posts) > available_slots:
        msg = f"{caller}: index needs {len(posts)} posts but only {available_slots} slots exist."
        if extra_hint:
            msg += "\n" + extra_hint
        raise SystemExit(msg)
    return posts
