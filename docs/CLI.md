# Telegram Video Automation CLI

The `main.py` entry point acts as the unified CLI for all operations.

## Setup
```bash
uv sync
```

## Usage
Run the CLI using `uv run main.py`:

```bash
uv run main.py [input_url] [options]
```

### Options
- `--url`: Download a single lesson.
- `--scan`: Scan the target site and update the video manifest.
- `--download`: Batch download videos from the manifest.
- `--archive`: Archive HTML pages listed in the manifest.
- `--force`: Force overwrite existing files.
- `--limit`: Limit operations to N items.
- `--visible`: Run Chrome in visible mode.
- `--verbose`: Enable debug logging.

## Examples
### Download a Single Lesson
```bash
uv run main.py "https://example.com/lesson" --visible
```

### Batch Processing
```bash
uv run main.py --scan
uv run main.py --download
uv run main.py --archive
```
