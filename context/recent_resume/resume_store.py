from typing import Dict, List, Optional

from utils.redis_client import RedisClient


class ResumeStore:
    """
    Two-layer resume context store.

    Layer 1 (session recent list):
    - key: session:{session_id}:recent_resumes
    - value: Redis List of candidate_id (newest first)

    Layer 2 (resume summary):
    - key: resume:summary:{candidate_id}
    - value: Redis Hash with ONLY:
      - name
      - summary
    """

    def __init__(
        self,
        redis_client=None,
        key_prefix: str = "session",
        list_name: str = "recent_resumes",
        max_size: int = 50,
        ttl_seconds: Optional[int] = 7 * 24 * 3600,
    ):
        self.client = redis_client or RedisClient.get_client()
        self.key_prefix = key_prefix
        self.list_name = list_name
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds

    def _recent_key(self, session_id: str) -> str:
        return f"{self.key_prefix}:{session_id}:{self.list_name}"

    def _summary_key(self, candidate_id: str) -> str:
        return f"resume:summary:{candidate_id}"

    def add(self, session_id: str, candidate_id: str) -> None:
        """
        Add candidate_id to recent list (deduplicated, newest first).
        """
        key = self._recent_key(session_id)
        with self.client.pipeline() as pipe:
            pipe.lrem(key, 0, candidate_id)
            pipe.lpush(key, candidate_id)
            pipe.ltrim(key, 0, self.max_size - 1)
            if self.ttl_seconds:
                pipe.expire(key, self.ttl_seconds)
            pipe.execute()

    def get(self, session_id: str, limit: Optional[int] = None) -> List[str]:
        """Get recent candidate ids (newest first)."""
        key = self._recent_key(session_id)
        if limit is None or limit <= 0:
            limit = self.max_size
        return self.client.lrange(key, 0, limit - 1)

    def remove(self, session_id: str, candidate_id: str) -> int:
        """Remove candidate_id from recent list."""
        key = self._recent_key(session_id)
        return int(self.client.lrem(key, 0, candidate_id))

    def clear(self, session_id: str) -> int:
        """Clear recent list for a session."""
        key = self._recent_key(session_id)
        return int(self.client.delete(key))

    def set_summary(self, candidate_id: str, name: str, summary: str) -> None:
        """Set resume summary (value includes ONLY name + summary)."""
        key = self._summary_key(candidate_id)
        with self.client.pipeline() as pipe:
            pipe.hset(key, mapping={"name": name or "", "summary": summary or ""})
            if self.ttl_seconds:
                pipe.expire(key, self.ttl_seconds)
            pipe.execute()

    def get_summary(self, candidate_id: str) -> Optional[Dict[str, str]]:
        """Get resume summary by candidate_id."""
        key = self._summary_key(candidate_id)
        data = self.client.hgetall(key)
        if not data:
            return None
        return {
            "name": data.get("name", ""),
            "summary": data.get("summary", ""),
        }

    def delete_summary(self, candidate_id: str) -> int:
        """Delete resume summary by candidate_id."""
        key = self._summary_key(candidate_id)
        return int(self.client.delete(key))

    def add_with_summary(self, session_id: str, candidate_id: str, name: str, summary: str) -> None:
        """Upsert summary first, then add candidate_id to recent list."""
        self.set_summary(candidate_id=candidate_id, name=name, summary=summary)
        self.add(session_id=session_id, candidate_id=candidate_id)

    def get_recent_summaries(self, session_id: str, limit: Optional[int] = None) -> List[Dict[str, str]]:
        """Get recent resume summaries with candidate_id + name + summary."""
        candidate_ids = self.get(session_id=session_id, limit=limit)
        if not candidate_ids:
            return []

        summaries: List[Dict[str, str]] = []
        for cid in candidate_ids:
            summary = self.get_summary(cid)
            if summary is None:
                summaries.append({"candidate_id": cid, "name": "", "summary": ""})
                continue
            summaries.append(
                {
                    "candidate_id": cid,
                    "name": summary["name"],
                    "summary": summary["summary"],
                }
            )
        return summaries
