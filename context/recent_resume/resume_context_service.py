from typing import Dict, List, Optional

from context.recent_resume.resume_store import ResumeStore


class ResumeContextService:
    """High-level service for recent resume summary context."""

    def __init__(self, store: Optional[ResumeStore] = None):
        self.store = store or ResumeStore()

    def get_recent_resume_summaries(self, session_id: str, limit: int = 10) -> List[Dict[str, str]]:
        """
        Return recent resume summaries for a session.

        Each item includes:
        - candidate_id
        - name
        - summary
        """
        return self.store.get_recent_summaries(session_id=session_id, limit=limit)

    def update_latest_view(self, session_id: str, candidate_id: str, name: str, summary: str) -> None:
        """
        Update latest viewed resume for a session.

        Behavior:
        - upsert summary key: resume:summary:{candidate_id}
        - move candidate_id to the head of recent list
        """
        self.store.add_with_summary(
            session_id=session_id,
            candidate_id=candidate_id,
            name=name,
            summary=summary,
        )

