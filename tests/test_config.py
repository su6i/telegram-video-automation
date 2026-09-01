import os
from unittest.mock import patch

from src.config import get_path, get_storage_config, load_config


def test_load_config_missing():
    with patch('os.path.exists', return_value=False):
        assert load_config() == {}

def test_get_storage_config_defaults():
    with patch('src.config._config_cache', {}):
        config = get_storage_config()
        assert config["base_dir"] == ".storage"
        assert config["downloads_dir"] == "downloads"

def test_get_path_resolves():
    with patch('src.config._config_cache', {}):
        assert get_path("downloads_dir") == "downloads"
        assert get_path("manifest_file") == os.path.join(".storage", "downloaded_video.txt")
