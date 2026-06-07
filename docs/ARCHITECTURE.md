# Architecture Overview

## Single Core, Multiple Shells
The project embraces a unified architecture where core logic is separated from interfaces.

### Core Modules
- `src/config.py`: Centralized configuration management reading from `config.yaml` and `.env`.
- `src/scrapers/`: Domain-specific scrapers.
- `src/media_library.py`: Logic for storing and indexing video files.
- `src/manifest_manager.py`: Manages the state of scraped and downloaded items.

### Interfaces
- `main.py`: The single, unified command-line entry point.
- Legacy shell scripts (`download.sh`, `scan.sh`, `upload.sh`): Preserved as simple wrappers calling into `main.py` and `uv` to ensure backward compatibility.

### Storage
All persistent data (manifests, scraped content, temp files) are stored cleanly in the `.storage/` directory to prevent workspace pollution, following Git best practices.
