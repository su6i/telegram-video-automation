#!/usr/bin/env python3
"""
Gate a distilled skill on leaking none of the source's expression.

`agent-constitution` is a public repository and the transcripts are someone
else's teaching. What may leave the vault is procedural knowledge in our own
words; what may never leave it is the expression — no transcript sentences, no
lesson titles, no course, site or instructor names.

Two independent checks, because they fail differently:

* **Banned terms** catch the names. They are derived from the manifest
  (course, section and lesson titles) so the list cannot drift out of date,
  plus an optional extra list in the vault for instructor and site names.
* **N-gram overlap** catches copied phrasing that no name list would ever
  contain. Any run of --n words shared with the transcript corpus is a hit.

    uv run tools/knowledge/check_skill_leak.py \
        --skill ../agent-constitution/skills/some-skill.md \
        --transcripts <vault>/data/transcripts

Exit status is 1 if anything leaked, so it can be a pre-commit gate.
"""
import argparse
import json
import os
import re
import sys
import unicodedata
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[2]))

from src.manifest_tracker import parse_manifest_line

DEFAULT_N = 8
MIN_TERM_LEN = 4

# Words too generic to be worth banning even when they appear in a title.
STOPWORDS = {
    "the", "and", "for", "with", "your", "you", "how", "why", "what", "from",
    "this", "that", "into", "over", "make", "made", "use", "using", "guide",
    "intro", "introduction", "overview", "part", "course", "lesson", "video",
    "videos", "tips", "best", "more", "new", "get", "got", "all", "one",
}


def normalize(text):
    """Lowercase, strip accents and punctuation, collapse whitespace."""
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def words(text):
    return normalize(text).split()


def ngrams(tokens, n):
    return {tuple(tokens[i:i + n]) for i in range(len(tokens) - n + 1)}


def strip_markdown(text):
    """Drop fenced code and inline code, which carry no source expression."""
    text = re.sub(r"```.*?```", " ", text, flags=re.S)
    return re.sub(r"`[^`]*`", " ", text)


def manifest_terms(manifest_path):
    """Course names, section names and lesson titles from the manifest."""
    terms = set()
    if not os.path.exists(manifest_path):
        return terms
    for line in open(manifest_path, encoding="utf-8"):
        line = line.strip()
        if line.startswith("# === "):
            terms.add(line[6:].split(" ===")[0].split("(")[0].strip())
        elif line.startswith("## --- "):
            terms.add(line[7:].replace(" ---", "").strip())
        else:
            # One parser for both manifest line formats (src/manifest_tracker).
            parsed = parse_manifest_line(line)
            if parsed:
                terms.add(parsed[1])
    return {t for t in terms if t}


def transcript_titles(transcripts_dir):
    titles = set()
    for p in sorted(Path(transcripts_dir).glob("*.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if data.get("title"):
            titles.add(str(data["title"]))
    return titles


def build_banned(terms, extra_path=None):
    """Multi-word phrases kept whole; single words kept only if distinctive."""
    phrases = set()
    for term in terms:
        norm = normalize(term)
        if not norm:
            continue
        toks = norm.split()
        if len(toks) > 1:
            phrases.add(norm)
        elif len(norm) >= MIN_TERM_LEN and norm not in STOPWORDS:
            phrases.add(norm)
    if extra_path and os.path.exists(extra_path):
        for line in open(extra_path, encoding="utf-8"):
            line = line.split("#")[0].strip()
            if line:
                phrases.add(normalize(line))
    return {p for p in phrases if p}


def find_banned(skill_text, banned):
    norm = normalize(strip_markdown(skill_text))
    padded = f" {norm} "
    return sorted(term for term in banned if f" {term} " in padded)


def corpus_ngrams(transcripts_dir, n):
    grams = set()
    for p in sorted(Path(transcripts_dir).glob("*.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        grams |= ngrams(words(data.get("text", "")), n)
    return grams


def find_overlap(skill_text, grams, n):
    toks = words(strip_markdown(skill_text))
    hits = [g for g in ngrams(toks, n) if g in grams]
    return sorted(" ".join(g) for g in hits)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--skill", required=True, action="append",
                    help="skill file to check (repeatable)")
    ap.add_argument("--transcripts", required=True, help="transcripts directory in the vault")
    ap.add_argument("--manifest", default=".storage/downloaded_video.txt")
    ap.add_argument("--extra-terms", help="newline-separated extra banned terms (vault file)")
    ap.add_argument("--n", type=int, default=DEFAULT_N,
                    help=f"n-gram length for the overlap test (default {DEFAULT_N})")
    args = ap.parse_args()

    transcripts_dir = Path(os.path.expanduser(args.transcripts))
    terms = manifest_terms(args.manifest) | transcript_titles(transcripts_dir)
    banned = build_banned(terms, args.extra_terms and os.path.expanduser(args.extra_terms))
    print(f"🔒 banned terms: {len(banned)} | building {args.n}-grams ...", flush=True)
    grams = corpus_ngrams(transcripts_dir, args.n)
    print(f"   corpus {args.n}-grams: {len(grams):,}")

    failed = False
    for skill_path in args.skill:
        path = Path(os.path.expanduser(skill_path))
        text = path.read_text(encoding="utf-8")
        term_hits = find_banned(text, banned)
        gram_hits = find_overlap(text, grams, args.n)

        if not term_hits and not gram_hits:
            print(f"✅ {path.name}: clean")
            continue

        failed = True
        print(f"❌ {path.name}: {len(term_hits)} banned term(s), {len(gram_hits)} copied phrase(s)")
        for t in term_hits[:20]:
            print(f"   term: {t}")
        for g in gram_hits[:20]:
            print(f"   phrase: {g}")
        if len(term_hits) > 20 or len(gram_hits) > 20:
            print("   ... truncated")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
