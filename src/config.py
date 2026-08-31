import os
import yaml

CONFIG_FILE = "config.yaml"

def load_config():
    """Loads text config.yaml into a dictionary."""
    if not os.path.exists(CONFIG_FILE):
        return {}
    with open(CONFIG_FILE, 'r') as f:
        return yaml.safe_load(f) or {}

_config_cache = load_config()

def get_storage_config():
    """Returns the 'storage' section from config with defaults."""
    storage = _config_cache.get('storage', {})
    
    # Defaults
    defaults = {
        "base_dir": ".storage",
        "downloads_dir": "downloads",
        "manifest_file": "downloaded_video.txt",
        "media_paths_file": "media_paths.json",
        "content_file": "scraped_content.json",
        "chrome_profile_dir": "chrome_profile",
        "failed_log": "failed_downloads.txt"
    }
    
    # Merge defaults
    for k, v in defaults.items():
        if k not in storage:
            storage[k] = v
            
    return storage

def get_path(key):
    """
    Resolves a path definition to an absolute or relative path string.
    Keys: base_dir, downloads_dir, manifest_file, etc.
    """
    conf = get_storage_config()
    
    if key == "base_dir":
        return conf["base_dir"]
    
    if key == "downloads_dir":
        return conf["downloads_dir"]
        
    if key in ["manifest_file", "media_paths_file", "content_file", "chrome_profile_dir", "failed_log"]:
        return os.path.join(conf["base_dir"], conf[key])
        
    return conf.get(key)
