"""Read a lesson's index and title out of a channel caption or a filename.

The channel carries two caption generations: the early uploads open with
"NNN - Title" on the first line, the later ones put the course and the
section first and the index only on the third line. Anything that reads a
caption back — the table of contents, the message map, the manifest
alignment — has to look at the header lines, not just the first one.
"""
import re
from typing import Optional, Tuple

# LRM/RLM markers the channel captions carry.
RTL_MARKS_RE = re.compile(r"[\u200e\u200f]")

# "**036 - Title**" on any of the caption's header lines. The early uploads
# open with "NNN - Title", the later ones carry the course and the section on
# the first two lines and the index only on the third, so anchoring on the
# first line alone misses most of the channel.
HEADER_INDEX_RE = re.compile(r'^[\s*_#\[\(]*0*(\d{1,4})\s*[-\u2013\u2014\.\:\|\]\)]\s*', re.M)
HEADER_LINES = 3


def extract_index_and_title(text: str) -> Tuple[Optional[int], str]:
    """Return (lesson number, title) from a caption or a filename.

    Searches the header lines rather than only the first one, and takes the
    title from the same line the number was found on. Returns (None, "")
    when no line carries an index.
    """
    if not text:
        return None, ""
    s = RTL_MARKS_RE.sub("", text)
    for line in s.split("\n")[:HEADER_LINES]:
        m = HEADER_INDEX_RE.match(line)
        if m:
            num = int(m.group(1))
            title = line[m.end():].strip().strip("*_").strip()
            # The oldest captions repeat "NNN - Title" after the course and
            # section words ("001 - - Course Intro 001 - Welcome!"): keep the
            # part after the last repeat of this lesson's own number.
            repeat = re.compile(rf'{num:03d}\s*[-\u2013\u2014\.\:\|]\s*')
            while True:
                dup = repeat.search(title)
                if not dup:
                    break
                title = title[dup.end():]
            title = re.sub(r'^[\s\-\u2013\u2014\.\:\|]+', '', title).strip()
            return num, title
    return None, ""


def safe_extract_number(text: str) -> int:
    """Extracts the lesson number from a caption/filename; RLM/LRM are ignored."""
    if not text:
        return 999999
    num, _ = extract_index_and_title(text)
    if num is not None:
        return num
    s = RTL_MARKS_RE.sub("", text)
    # Looser fallbacks for filenames and unseparated numbering (001, [001], #001)
    patterns = [
        r'^\s*#?\s*0*(\d{1,4})\s*[^\d]',
        r'^\s*#?\s*0*(\d{1,4})\s*$',
    ]
    for pattern in patterns:
        m = re.search(pattern, s)
        if m:
            return int(m.group(1))
    return 999999
