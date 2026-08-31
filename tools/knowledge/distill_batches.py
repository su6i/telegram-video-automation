#!/usr/bin/env python3
"""
Cut the transcripts into per-section distillation batches for a worker.

Step 6 turns the transcripts into agent skills. That is an LLM job over ~3.5M
characters, which belongs on a $0 worker, not in an architect session — so this
script does the deterministic half: it groups the transcripts the way the course
already groups them (one batch per section, which is what a skill is shaped
like), writes a self-contained prompt per batch, and reports the sizes so the
batches can be dispatched.

    uv run tools/knowledge/distill_batches.py --out <vault>/data/distill

Everything it writes contains transcript text, so it lands in the vault and
never in this repository (rule 035). Each batch's output must pass
check_skill_leak.py before it is committed to agent-constitution.
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[2]))

import src.manifest_tracker as manifest_tracker

# Sections that teach nothing transferable — housekeeping, community links,
# discount codes. They produce no skill.
DEFAULT_SKIP = ("course intro", "discounts", "updates", "community")

PROMPT = """# Distillation task — one agent skill from one course section

You are writing a reusable skill file for an agent library. Below are the
transcripts of {count} lessons that together cover a single topic.

## What to produce

A single Markdown file in this exact shape:

```markdown
---
name: <kebab-case-topic>
description: <one line, what an agent can do after reading this>
version: 1.0.0
updated: {today}
---

# <Topic>

## When to use this
...

## Method
<the procedure, as numbered steps a competent agent can follow>

## Decision rules
<the judgment calls: when to choose what, and why>

## Pitfalls
<what goes wrong, and the symptom that reveals it>
```

## Hard constraints — a violation fails the automated gate

1. **Write in your own words.** Never copy a sentence, a clause, or a
   distinctive phrase from the transcripts. An automated 8-gram overlap test
   runs against the full corpus; any eight consecutive words shared with a
   transcript fails the file.
2. **Name nothing.** No course name, no section name, no lesson title, no
   instructor name, no site or brand the material is hosted on. Tool and
   product names that are genuinely part of the method (a public API, a codec,
   a file format) are fine.
3. **Keep only what transfers.** The method, the decision rules, the
   checklist. Drop the anecdotes, the promises, the sales material.
4. **Say nothing you cannot support** from the material. Do not invent
   specifics to fill a section — cut the section instead.

## Transcripts

{body}
"""


def slugify(text):
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return re.sub(r"-{2,}", "-", s) or "section"


def transcript_text(transcripts_dir, index):
    """The transcript whose filename starts with this lesson index."""
    for p in sorted(Path(transcripts_dir).glob(f"{index}_*.json")):
        try:
            return json.loads(p.read_text(encoding="utf-8")).get("text", "")
        except Exception:
            return ""
    return ""


def group_sections(videos, skip):
    """[(course, section, [indexes])] in manifest order, admin sections dropped."""
    order, groups = [], {}
    for v in videos:
        key = (v["course"], v["section"])
        if any(s in v["section"].lower() for s in skip):
            continue
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(v["index"])
    return [(c, s, groups[(c, s)]) for c, s in order]


def split_batches(indexes, texts, max_chars):
    """Split one section into parts that each fit a worker's context."""
    batches, current, size = [], [], 0
    for idx in indexes:
        length = len(texts.get(idx, ""))
        if current and size + length > max_chars:
            batches.append(current)
            current, size = [], 0
        current.append(idx)
        size += length
    if current:
        batches.append(current)
    return batches


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--out", required=True, help="batch directory (in the vault)")
    ap.add_argument("--transcripts",
                    default=os.path.expanduser(
                        "~/.local/share/agent-projects/telegram-video-automation/data/transcripts"))
    ap.add_argument("--manifest", default=".storage/downloaded_video.txt")
    ap.add_argument("--max-chars", type=int, default=120_000,
                    help="split a section whose transcripts exceed this")
    ap.add_argument("--skip-section", action="append", default=None,
                    help="substring of a section name to drop (repeatable)")
    ap.add_argument("--today", default=None, help="date stamp for the skill frontmatter")
    args = ap.parse_args()

    from datetime import date
    today = args.today or date.today().isoformat()
    skip = tuple(s.lower() for s in (args.skip_section or DEFAULT_SKIP))

    manifest_tracker.MANIFEST_FILE = args.manifest
    videos = manifest_tracker.get_all_manifest_videos()
    if not videos:
        print(f"❌ no lessons read from {args.manifest}")
        return 1

    transcripts_dir = Path(os.path.expanduser(args.transcripts))
    texts = {v["index"]: transcript_text(transcripts_dir, v["index"]) for v in videos}
    missing = [i for i, t in texts.items() if not t]

    out_dir = Path(os.path.expanduser(args.out))
    out_dir.mkdir(parents=True, exist_ok=True)

    sections = group_sections(videos, skip)
    written, total_chars = 0, 0

    print(f"{'batch':44} {'lessons':>7} {'chars':>9}")
    for course, section, indexes in sections:
        usable = [i for i in indexes if texts.get(i)]
        if not usable:
            continue
        parts = split_batches(usable, texts, args.max_chars)
        for n, part in enumerate(parts, 1):
            suffix = f"-part{n}" if len(parts) > 1 else ""
            name = f"{slugify(course)}--{slugify(section)}{suffix}"
            body = "\n\n---\n\n".join(texts[i] for i in part)
            prompt = PROMPT.format(count=len(part), today=today, body=body)
            (out_dir / f"{name}.md").write_text(prompt, encoding="utf-8")
            written += 1
            total_chars += len(body)
            print(f"{name:44} {len(part):>7} {len(body):>9,}")

    print(f"\n📊 {written} batch(es) -> {out_dir}")
    print(f"   transcript characters: {total_chars:,} (~{total_chars // 4:,} tokens)")
    print(f"   sections skipped as admin: {', '.join(skip)}")
    if missing:
        print(f"   ⚠️ {len(missing)} lesson(s) have no transcript: {', '.join(sorted(missing)[:12])}"
              + (" ..." if len(missing) > 12 else ""))
    print("\nEach batch is one worker call. Gate every result with "
          "check_skill_leak.py before it goes near agent-constitution.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
