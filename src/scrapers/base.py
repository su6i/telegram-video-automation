from abc import ABC, abstractmethod


class BaseScraper(ABC):
    @abstractmethod
    def get_video_links(self, limit: int | None = None) -> list[dict]:
        """
        Scrapes video links and metadata.
        Returns a list of dictionaries with keys:
        - title: str
        - url: str (m3u8 or mp4)
        - date: datetime (for sorting)
        - sort_index: int (optional, as fallback)
        """
