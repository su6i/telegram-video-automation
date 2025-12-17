from abc import ABC, abstractmethod
from typing import List, Dict, Optional
from datetime import datetime

class BaseScraper(ABC):
    @abstractmethod
    def get_video_links(self, limit: Optional[int] = None) -> List[Dict]:
        """
        Scrapes video links and metadata.
        Returns a list of dictionaries with keys:
        - title: str
        - url: str (m3u8 or mp4)
        - date: datetime (for sorting)
        - sort_index: int (optional, as fallback)
        """
        pass
