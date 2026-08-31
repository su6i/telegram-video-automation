# Architecture Overview

## Single Core, Multiple Shells
The project embraces a unified architecture where core logic is separated from interfaces.

### Core Modules
- `src/config.py`: Centralized configuration management reading from `config.yaml` and `.env`.
- `src/scrapers/`: Domain-specific scrapers.
- `src/media_library.py`: Logic for storing and indexing video files.
- `src/manifest_manager.py`: Manages the state of scraped and downloaded items.
- `src/manifest_tracker.py`: Reads and writes the per-lesson upload status in
  `.storage/downloaded_video.txt`. `parse_manifest_line` is the single place that
  understands both line formats the manifest carries — the compact
  `NNN_Title | URL` it is generated in and the `NNN | TITLE | URL | STATUS` it is
  expanded into once a status is recorded — so every reader agrees on what is
  pending, uploaded or failed.
- `src/caption_index.py`: Reads a lesson's index and title out of a channel caption
  or a filename, off whichever header line carries it. Shared by the table of
  contents and the message map so the two never disagree.

### Interfaces
- `main.py`: The single, unified command-line entry point.
- Legacy shell scripts (`download.sh`, `scan.sh`, `upload.sh`): Preserved as simple wrappers calling into `main.py` and `uv` to ensure backward compatibility.

### Storage
All persistent data (manifests, scraped content, temp files) are stored cleanly in the `.storage/` directory to prevent workspace pollution, following Git best practices.
