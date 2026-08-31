"""
Identifiers of the site being scraped.

Rule 035: the site's name, domain, product slugs and page titles are personal
data — they never live in the repository. They are read at runtime from a
profile file outside the tree (the vault), pointed at by SITE_PROFILE or found
at .storage/site_profile.json, which is a symlink into the vault.

Shape:
    {
      "course_titles": {"<product-slug or page title>": "<display name>"},
      "default_course": "Unknown Course"
    }

A missing profile is not an error: the scraper then uses whatever the page
itself says, which is the generic behaviour.
"""
import json
import os

DEFAULT_PATH = os.path.join(".storage", "site_profile.json")

_cache = None


def load_profile():
    global _cache
    if _cache is None:
        path = os.getenv("SITE_PROFILE", DEFAULT_PATH)
        try:
            with open(path, encoding="utf-8") as f:
                _cache = json.load(f)
        except (OSError, ValueError):
            _cache = {}
    return _cache


def course_title_for(key, fallback=None):
    """Display name for a product slug or a raw page title."""
    titles = load_profile().get("course_titles", {})
    return titles.get(key, fallback if fallback is not None else key)
