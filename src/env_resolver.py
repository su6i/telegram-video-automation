"""Resolve the path to this project's .env file in the personal-data vault.

See agent-constitution/rules/035-data-vault.md. The real .env file lives
outside this repo, in ~/.local/share/agent-projects/telegram-video-automation/secrets/.env
(or an override location below) — never inside the working tree.
"""
import os
from pathlib import Path

PROJECT_SLUG_FALLBACK = "telegram-video-automation"


def _project_slug() -> str:
    if s := os.getenv("AGENT_PROJECT_SLUG"):
        return s.lower()
    return PROJECT_SLUG_FALLBACK


def _vault_root() -> Path:
    if o := os.getenv("TELEGRAM_VIDEO_AUTOMATION_DATA_DIR"):
        return Path(o).expanduser()
    xdg = os.getenv("XDG_DATA_HOME")
    base = Path(xdg).expanduser() if xdg else Path.home() / ".local" / "share"
    return base / "agent-projects" / _project_slug()


def env_path() -> Path:
    """Absolute path to this project's .env file in the personal-data vault."""
    return _vault_root() / "secrets" / ".env"
