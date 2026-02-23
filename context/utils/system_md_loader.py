import os
from typing import Optional


class SystemMarkdownLoader:
    """
    Loader for system markdown file with optional hot reload.

    Designed for a single file (e.g. context/data/system_prompt.md).
    """

    def __init__(self, file_path: str, hot_reload: bool = True):
        self.file_path = file_path
        self.hot_reload = hot_reload
        self._cache_content: Optional[str] = None
        self._cache_mtime: Optional[float] = None

    def set_hot_reload(self, enabled: bool) -> None:
        self.hot_reload = bool(enabled)

    def read(self) -> str:
        """
        Read markdown content.

        Behavior:
        - hot_reload=False: first load then always use cache
        - hot_reload=True: reload on file mtime change
        """
        if self._cache_content is None:
            return self._load_and_cache() or ""

        if not self.hot_reload:
            return self._cache_content

        try:
            mtime = os.path.getmtime(self.file_path)
        except OSError:
            return self._cache_content

        if self._cache_mtime == mtime:
            return self._cache_content

        return self._load_and_cache() or self._cache_content

    def invalidate(self) -> None:
        self._cache_content = None
        self._cache_mtime = None

    def _load_and_cache(self) -> Optional[str]:
        if not os.path.exists(self.file_path):
            return self._cache_content

        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                content = f.read()
            self._cache_content = content
            self._cache_mtime = os.path.getmtime(self.file_path)
            return content
        except Exception:
            return self._cache_content

