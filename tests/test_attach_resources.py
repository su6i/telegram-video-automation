"""Zipping 14 GB of already-compressed media must not deflate it."""
import sys
import zipfile
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1] / "tools" / "knowledge"))

from attach_resources import compression_for  # noqa: E402


def test_precompressed_media_is_stored():
    assert compression_for(Path("a/Clip.MP4")) == zipfile.ZIP_STORED
    assert compression_for(Path("a/track.wav")) == zipfile.ZIP_STORED
    assert compression_for(Path("a/pack.zip")) == zipfile.ZIP_STORED


def test_everything_else_is_deflated():
    assert compression_for(Path("a/notes.txt")) == zipfile.ZIP_DEFLATED
    assert compression_for(Path("a/project.prproj")) == zipfile.ZIP_DEFLATED
