"""
Caption construction for Telegram posts.

Extracted from scripts/process_and_upload.py so the exact caption that will be
sent can be rendered offline (scripts/preview_captions.py) before any upload.
"""
import re


def format_description_markdown(text):
    """
    Format description text for beautiful Telegram display.
    - Makes headers BOLD
    - Preserves indentation and newlines where logical
    """
    if not text:
        return text
    
    EXCLUDED_WORDS = {'Both', 'His', 'Their', 'Once', 'The', 'And', 'With', 'From', 'This', 'That', 'These', 'Those'}
    
    # Improved patterns: handle colons correctly
    header_patterns = [
        r'\b(Your Robot Buddy)\s*',
        r'\b(Superman)\s*',
        r'\b(Swimming with sharks)\s*',
        r'\b(Game of [Tt]hrones)\b',
        r'\b(Wizard)\s*(?=an image)',
        r'\b(Pirate)\s*(?=\[insert)',
        r'\b(EXTREMELY IMPORTANT[:!]?)\s*',
        r'\b(IMPORTANT NOTE:?|IMPORTANT[:!]?)\s*',
        r'\b(NOTE:?)\s*',
        r'\b(TIP:?)\s*',
        r'\b(WARNING[:!]?)\s*',
        r'\b(Lesson Recap:?)\s*',
        r'\b(Prompt Templates?:?)\s*',
        r'\b(\d+/\d+\s+Update[:!]?)\s*',
        r'\b(How to [^:\n]+:?)\s*',
    ]
    
    # Each matched header is swapped for a sentinel that no later pattern can
    # match. Wrapping in @@@ markers instead let "IMPORTANT NOTE:" be split a
    # second time by the "NOTE:" pattern, which leaked @@@ into the caption.
    marked = {}

    def _protect(match):
        key = f"\x01H{len(marked)}\x01"
        marked[key] = match.group(1)
        return f"\n\n{key}\n"

    processed = text
    for pattern in header_patterns:
        processed = re.sub(pattern, _protect, processed)
    
    lines = processed.split('\n')
    formatted_lines = []
    
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            formatted_lines.append('')
            continue
        
        # A parked inline link is body text; bolding it would wrap the whole
        # link in ** and hide it behind a header.
        if '\x02' in stripped:
            formatted_lines.append(stripped)
            continue

        is_protected = False
        if stripped in marked:
            stripped = marked[stripped]
            is_protected = True
        
        # Skip if already has Markdown formatting
        if (stripped.startswith('**') and stripped.endswith('**')) or stripped.startswith('['):
            formatted_lines.append(stripped)
            continue
            
        is_header = is_protected
        
        # Additional detection for unprotected lines
        if not is_header:
            # DON'T treat list items as headers even if Title Cased
            if re.match(r'^(\d+\.|[\-•·*]|->|=>|\.)\s+', stripped) or stripped in EXCLUDED_WORDS:
                is_header = False
            elif re.search(r'^(EXTREMELY\s+)?(IMPORTANT|NOTE|TIP|WARNING|RECAP|HOW TO)\b', stripped.upper()):
                is_header = True
            elif len(stripped) < 45 and not stripped.endswith(('.', '!', '?')) and 1 <= len(stripped.split()) <= 6:
                words = stripped.split()
                # Check for Title Case - Lowered threshold to 0.6 to catch "Text to Video Links"
                capitalized = sum(1 for w in words if w and (w[0].isupper() or not w[0].isalpha()))
                if capitalized >= len(words) * 0.6 and words[0] not in EXCLUDED_WORDS:
                    is_header = True
            elif (stripped.endswith(':') or stripped.isupper()) and len(stripped) < 50:
                is_header = True
        
        if is_header:
            if formatted_lines and formatted_lines[-1] != '':
                formatted_lines.append('')
            formatted_lines.append(f"**{stripped}**")
        else:
            formatted_lines.append(stripped)

    # Join and clean up excessive newlines (max 2)
    result = '\n'.join(formatted_lines)

    # Safety net: never publish a stray sentinel or an empty bold line.
    result = re.sub(r'\x01H\d+\x01', '', result)
    result = re.sub(r'(?m)^\*{2,}$', '', result)

    result = re.sub(r'\n{3,}', '\n\n', result)

    return result.strip()


# Headers the scraper is known to emit; they always start their own line.
PROTECTED_HEADERS = {
    'Your Robot Buddy', 'Superman', 'Swimming with sharks', 'Game of Thrones',
    'Wizard', 'Pirate', 'EXTREMELY IMPORTANT', 'IMPORTANT NOTE', 'Lesson Recap',
    'Prompt Template', 'Continued', 'Example Prompts',
}

# A bullet/number that the scraper split away from the text it belongs to.
LONE_MARKER_RE = re.compile(r'^([\-•·*]|\d+\.)$')
# Punctuation the scraper split away from the end of the previous sentence.
LONE_PUNCT_RE = re.compile(r'^[.,;:!?…]+$')
# A line that already carries its own bullet/number and its text.
LIST_ITEM_RE = re.compile(r'^(\d+\.|[\-•·*]|->|=>|>)\s+')


def is_list_item_flag(text):
    """True when the line already carries its own bullet or number."""
    return bool(LIST_ITEM_RE.match(text))


def _is_header_line(text):
    """A line that stands on its own: protected phrase, SHOUTING, or 'Label:'."""
    upper = text.upper()
    if any(h.upper() in upper for h in PROTECTED_HEADERS):
        return True
    if text.isupper() and len(text) < 40:
        return True
    return text.rstrip().endswith(':') and len(text) < 60


def unfragment_text(text):
    """
    Rejoin lines the scraper tore apart.

    The site wraps inline emphasis in its own elements, so a single sentence
    arrives as "From the pop-up menu, select" / "Settings" / ".", and a bullet
    arrives as "•" / "Go to the ...". Everything is glued back onto the line it
    belongs to, while real headers and real list items keep their own line.

    The rule is the buffer's last character: a line that does not end in
    terminal punctuation is an unfinished sentence, so the next line continues
    it unless that line is itself a list item or a header.
    """
    if not text:
        return ""

    out = []
    buf = ""
    awaiting_marker_text = False

    def flush():
        nonlocal buf
        if buf:
            out.append(buf.rstrip())
            buf = ""

    for line in text.split('\n'):
        stripped = line.strip()

        if not stripped:
            flush()
            out.append("")
            awaiting_marker_text = False
            continue

        # "•" alone: keep the marker and wait for the text that belongs to it.
        if LONE_MARKER_RE.match(stripped):
            flush()
            buf = stripped + " "
            awaiting_marker_text = True
            continue

        # "." alone, or ", or simply ..." — punctuation the scraper split off
        # the end of the previous line. Glue it back without a space.
        if buf and (LONE_PUNCT_RE.match(stripped) or stripped[0] in ',;:'):
            buf = buf.rstrip() + stripped
            continue

        if not buf:
            buf = stripped
            continue

        if awaiting_marker_text:
            buf += stripped
            awaiting_marker_text = False
            continue

        buffer_closed = buf.rstrip()[-1] in '.!?'
        is_list_item = is_list_item_flag(stripped)

        # A bold header the scraper tore in two: "IMPORTANT" then "NOTE:".
        # Only an all-caps buffer without its own colon may absorb the next
        # header line, so "QUICK UPDATE:" still keeps its body separate.
        if (buf.rstrip().isupper() and not buf.rstrip().endswith(':')
                and len(buf) < 40 and len(stripped) < 40
                and stripped.rstrip(':').isupper()
                and not is_list_item_flag(stripped)):
            buf = buf.rstrip() + " " + stripped
            continue

        if is_list_item or _is_header_line(stripped) or _is_header_line(buf) or buffer_closed:
            should_join = False
        else:
            # An unfinished sentence continues into a lowercase line or into a
            # short unpunctuated fragment (a torn-off bold span); a complete
            # sentence of its own starts a new line.
            starts_lower = stripped[0].islower() if stripped[0].isalpha() else False
            is_fragment = len(stripped) < 50 and stripped[-1] not in '.!?'
            should_join = starts_lower or is_fragment

        if should_join:
            buf += " " + stripped
        else:
            flush()
            buf = stripped

    flush()
    return "\n".join(out)


def validate_caption(caption):
    """
    Validate and fix caption before sending to Telegram.
    Ensures all Markdown markers are properly closed and protected.
    """
    if not caption:
        return caption

    # 1. Protect Markdown Links [text](url) from the underscore escaping below.
    #    The sentinel must survive step 2 untouched, so it carries no character
    #    that gets escaped — an underscored token would come back as
    #    MARKDOWN\_LINK\_PLACEHOLDER\_0 and never match on restore.
    links = re.findall(r'\[([^\]]+)\]\(([^)]+)\)', caption)
    placeholders = {}
    for i, (text, url) in enumerate(links):
        placeholder = f"\x00LINK{i}\x00"
        caption = caption.replace(f"[{text}]({url})", placeholder)
        placeholders[placeholder] = f"[{text}]({url})"

    # 2. Handle Underscores safely (escape them so they don't trigger italics)
    caption = caption.replace('_', r'\_')

    # 3. Restore Links (URLs should NOT have escaped underscores)
    for placeholder, original_link in placeholders.items():
        caption = caption.replace(placeholder, original_link)

    # 4. Fix unbalanced Bold (**) markers
    bold_count = caption.count('**')
    if bold_count % 2 != 0:
        last_pos = caption.rfind('**')
        if last_pos > len(caption) - 15:  # Near end
            caption = caption[:last_pos] + caption[last_pos + 2:]  # Strip
        else:
            caption += '**'  # Close

    # 5. Fix unbalanced Code (`) markers
    backtick_count = caption.count('`')
    if backtick_count % 2 != 0:
        last_pos = caption.rfind('`')
        caption = caption[:last_pos] + caption[last_pos + 1:]

    return caption


# Standard Telegram limit for a media caption. Premium accounts support 2048,
# but we use 1024 for universal compatibility.
CAPTION_LIMIT = 1024

# Appended to a caption whose description continues in follow-up messages.
OVERFLOW_MARKER = "\n\n⬇️ **(See next message)**"


def _label_for(url):
    """Anchor text for a link whose only label was "CLICK HERE"."""
    host = re.sub(r'^https?://(www\.)?', '', url or '').split('/')[0]
    return host or "Link"


def _safe_anchor(text):
    """Telegram's legacy Markdown ends a link text at the first "]"."""
    return text.replace('[', '(').replace(']', ')')


def build_caption(meta, extra, fallback_title, caption_limit=CAPTION_LIMIT):
    """
    Build the caption for one video.

    meta            parsed manifest line (course/section/index/line_title/url) or None
    extra           scraped_content entry for meta['url'] (description + links) or None
    fallback_title  title derived from the file when the manifest has nothing

    Returns (caption, overflow_text). overflow_text is the part of the
    description that did not fit and must be sent as follow-up messages.
    """
    if not meta:
        return validate_caption(f"**{fallback_title}**"), ""

    # HEADER (Professional Bold Format)
    header_parts = [f"**{meta['course']}**"]
    if meta['section'] and meta['section'] != "General":
        header_parts.append(f"**{meta['section']}**")

    final_title = meta['line_title'] if meta['line_title'] else fallback_title
    header_parts.append(f"**{meta['index']} - {final_title}**")

    caption = "\n".join(header_parts) + "\n\n"
    full_desc = ""
    overflow_text = ""

    if extra:
        desc = extra.get('description', '')

        # --- ROBUST COMMENT STRIPPING (Telegram Output Only) ---
        desc = re.split(r'(?i)Comments\s*\n\s*\d+', desc)[0]
        desc = re.split(r'(?i)Post Comment', desc)[0]
        desc = re.split(r'(?i)\n\d+\s+Comments', desc)[0]
        desc = re.split(r'(?m)^\d+ (minutes|hours|days|weeks|months) ago', desc)[0]
        desc = re.split(r'(?m)^REPLY\s*\n', desc)[0]

        # Inline <script> wrappers the scraper picked up along with the text.
        desc = re.sub(r'(?m)^\s*//\s*<!\[CDATA\[.*$', '', desc)
        desc = re.sub(r'(?m)^\s*//\s*\]\]>.*$', '', desc)
        desc = re.sub(r'(?is)<script.*?</script>', '', desc)
        desc = desc.strip()

        # The scraper tears sentences apart; rejoin before matching link anchors,
        # otherwise an anchor text spanning two fragments is never found.
        desc = unfragment_text(desc)

        # Process Links: Inline first.
        # Longest anchor first, and every inlined link is parked behind a
        # sentinel: otherwise a short anchor ("FLUX LORA") gets linked inside
        # the text a longer anchor ("Go to the FLUX LORA ... TRAINER") is about
        # to link, producing a nested [[..](..)](..) that Telegram mangles.
        remaining = []
        inlined = {}
        source_links = list(enumerate(extra.get('links') or []))
        source_links.sort(key=lambda pair: -len(pair[1].get('text') or ''))

        for order, link in source_links:
            url = link['url']
            orig_text = link['text']

            # Clean anchor text for matching. The scraper keeps the list
            # bullet inside the anchor text; leaving it in both doubles the
            # bullet ("• [• Sony ZV-e10]") and blocks the match against the
            # de-bulleted description, which is what pushed whole link blocks
            # into the header instead of inlining them.
            match_text = re.sub(r'(?i):\s*CLICK\s*HERE', '', orig_text)
            match_text = re.sub(r'(?i)CLICK\s*HERE', '', match_text)
            match_text = re.sub(r'^[•·*\-]\s*', '', match_text).strip(": ")

            if not match_text:
                match_text = _label_for(url)

            # Website might have blue bullets, scraper might have • or . or -
            clean_desc = re.sub(r'^[•·*.\-]\s+', '', desc, flags=re.MULTILINE)

            if match_text.lower() in clean_desc.lower():
                # swallow the trailing ":" of "Anchor text: CLICK HERE" so it
                # does not dangle after the rendered link
                pattern = re.compile(rf"(?i)(?:[•·*.\-]\s*)?{re.escape(match_text)}\s*:?", re.IGNORECASE)
                if pattern.search(desc):
                    key = f"\x02L{len(inlined)}\x02"
                    inlined[key] = f"[{_safe_anchor(match_text)}]({url})"

                    def _swap(m, key=key):
                        # Only a match that opens its line is a list entry; one
                        # inside a sentence must not grow a bullet. The pattern
                        # eats the whitespace after the anchor, so put it back
                        # or the sentence runs into the link.
                        at_line_start = m.start() == 0 or m.string[m.start() - 1] == '\n'
                        trailing = ' ' if m.group(0) != m.group(0).rstrip() else ''
                        return ("• " if at_line_start else "") + key + trailing

                    desc = pattern.sub(_swap, desc)
                    continue  # Successfully inlined, don't add to header

            remaining.append((order, link))

        remaining_links = [link for _order, link in sorted(remaining)]

        # 🔗 LINKS Header (Only for those not inlined)
        if remaining_links:
            caption += "🔗 **Links:**\n"
            for link in remaining_links:
                link_text = link['text']
                link_text = re.sub(r'(?i):\s*CLICK\s*HERE', '', link_text)
                link_text = re.sub(r'(?i)CLICK\s*HERE', '', link_text)
                link_text = re.sub(r'^[•·*\-]\s*', '', link_text).strip(": ")
                if not link_text:
                    link_text = _label_for(link['url'])
                caption += f"• [{_safe_anchor(link_text)}]({link['url']})\n"
            caption += "\n"

        # 📝 INFO (The updated description with inline links)
        if desc:
            desc = re.sub(r'(?i)CLICK\s*HERE\s*:?\s*', '', desc)

            # Deduplicate Title & Section: drop leading lines that repeat them
            clean_title = final_title.lower().strip()
            clean_section = meta['section'].lower().strip() if meta.get('section') else ""

            new_desc_lines = []
            skipped_header = False

            for line in desc.split('\n'):
                line_lower = line.lower().strip()
                if not line_lower:
                    new_desc_lines.append(line)
                    continue

                is_dup = (clean_title in line_lower or line_lower in clean_title) or \
                         (clean_section and (clean_section in line_lower or line_lower in clean_section))

                if not skipped_header and is_dup and len(line_lower) > 3:
                    continue
                else:
                    # Once we hit a non-header line, stop skipping
                    skipped_header = True
                    new_desc_lines.append(line)

            desc = "\n".join(new_desc_lines).strip(" :- \n\r")
            desc = format_description_markdown(desc)  # ✅ Make headers bold
            desc = re.sub(r'\n{3,}', '\n\n', desc).strip()

            for key, rendered in inlined.items():
                desc = desc.replace(key, rendered)

            full_desc = desc

    if full_desc:
        current_len = len(caption) + len("📝 **Info:**\n")
        remaining = caption_limit - current_len - len(OVERFLOW_MARKER) - 10

        if remaining < 120:
            # Header and links already fill the caption: send the whole
            # description as follow-up messages instead of a useless stub.
            overflow_text = full_desc
            caption += OVERFLOW_MARKER.strip()
        else:
            visible, overflow_text = _safe_cut(full_desc, remaining)
            caption += f"📝 **Info:**\n{visible}"
            if overflow_text:
                caption += OVERFLOW_MARKER

    caption = caption.rstrip()

    # Hard guarantee: the description split above does not account for the
    # header and the 🔗 Links block, so a lesson with many links could still
    # exceed the limit — Telegram rejects such a caption outright.
    caption, overflow_text = _enforce_caption_limit(caption, overflow_text, caption_limit)

    return validate_caption(caption), validate_caption(overflow_text) if overflow_text else ""


def _is_balanced(text):
    """No half-open **bold** span and no half-open [link] in this slice."""
    return text.count('**') % 2 == 0 and text.count('[') == text.count(']')


def _safe_cut(text, limit):
    """
    Split text into (head, tail) with head no longer than limit.

    Cuts on the largest natural boundary that leaves the markdown intact —
    breaking inside **a bold header** or a [link](url) publishes a caption with
    a stray ** or a raw URL, so such a boundary is rejected and the next one
    further back is tried.
    """
    text = text.strip()
    if limit <= 0:
        return "", text
    if len(text) <= limit:
        return text, ""

    floor = limit * 0.5
    for probe in ('\n\n', '\n', '. ', '? ', '! ', ' '):
        pos = text.rfind(probe, 0, limit)
        while pos > floor:
            head = text[:pos + len(probe)]
            if _is_balanced(head):
                return head.strip(), text[pos + len(probe):].strip()
            pos = text.rfind(probe, 0, pos)

    # No safe boundary at all: keep the markdown intact and send everything as
    # follow-up messages rather than publishing a broken caption.
    return "", text


def _enforce_caption_limit(caption, overflow_text, caption_limit):
    """Move whatever does not fit into the caption to the front of the overflow."""
    if len(caption) <= caption_limit:
        return caption, overflow_text

    if caption.endswith(OVERFLOW_MARKER.strip()):
        caption = caption[:-len(OVERFLOW_MARKER.strip())].rstrip()

    head, moved = _safe_cut(caption, caption_limit - len(OVERFLOW_MARKER))
    caption = (head + OVERFLOW_MARKER) if moved else head
    if moved:
        overflow_text = (moved + "\n\n" + overflow_text).strip() if overflow_text else moved
    return caption, overflow_text
