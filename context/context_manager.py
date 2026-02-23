import os
from typing import Any, Dict, List, Optional

from context.recent_resume import ResumeContextService
from context.utils import SystemMarkdownLoader


class ContextManager:
    """
    Core context orchestrator.

    Responsibilities:
    - Build system prompt from context/data/system_prompt.md
    - Default inject recent resume summaries
    - Keep skill/function and history handling as upstream logic (pass-through)
    """

    def __init__(
        self,
        system_prompt_path: Optional[str] = None,
        system_prompt_hot_reload: bool = True,
        recent_resume_limit: int = 5,
        resume_context_service: Optional[ResumeContextService] = None,
    ):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        default_prompt_path = os.path.join(base_dir, "data", "system_prompt.md")
        prompt_path = system_prompt_path or default_prompt_path

        self.system_loader = SystemMarkdownLoader(
            file_path=prompt_path,
            hot_reload=system_prompt_hot_reload,
        )
        self.recent_resume_limit = recent_resume_limit
        self.resume_context_service = resume_context_service or ResumeContextService()

    def build_system_prompt(
        self,
        session_id: str,
        runtime_info: Optional[Dict[str, Any]] = None,
        recent_limit: Optional[int] = None,
    ) -> str:
        """
        Build final system prompt:
        - base system markdown
        - recent resume summaries block (default loaded)
        - optional runtime info block
        """
        base_prompt = (self.system_loader.read() or "").strip()
        blocks: List[str] = [base_prompt] if base_prompt else []

        block_limit = recent_limit if recent_limit is not None else self.recent_resume_limit
        recent_block = self._build_recent_resume_block(session_id=session_id, limit=block_limit)
        if recent_block:
            blocks.append(recent_block)

        runtime_block = self._build_runtime_info_block(runtime_info)
        if runtime_block:
            blocks.append(runtime_block)

        return "\n\n".join(blocks).strip()

    def build_payload(
        self,
        session_id: str,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        runtime_info: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Build model payload.

        Note:
        - history/messages and trim policy stay in existing upstream logic
        - this class does not alter message ordering or trim behavior
        """
        system_prompt = self.build_system_prompt(
            session_id=session_id,
            runtime_info=runtime_info,
        )
        return {
            "system_prompt": system_prompt,
            "messages": messages,
            "tools": tools or [],
        }

    def get_recent_resume_summaries(self, session_id: str, limit: int = 10) -> List[Dict[str, str]]:
        """Return recent resume summaries for session."""
        return self.resume_context_service.get_recent_resume_summaries(session_id=session_id, limit=limit)

    def update_latest_resume_view(
        self,
        session_id: str,
        candidate_id: str,
        name: str,
        summary: str,
    ) -> None:
        """Update latest viewed resume info for session."""
        self.resume_context_service.update_latest_view(
            session_id=session_id,
            candidate_id=candidate_id,
            name=name,
            summary=summary,
        )

    def set_system_prompt_hot_reload(self, enabled: bool) -> None:
        self.system_loader.set_hot_reload(enabled)

    def reload_system_prompt(self) -> None:
        self.system_loader.invalidate()

    def _build_recent_resume_block(self, session_id: str, limit: int) -> str:
        items = self.get_recent_resume_summaries(session_id=session_id, limit=limit)
        if not items:
            return ""

        lines = ["## 最近浏览简历摘要"]
        for item in items:
            candidate_id = item.get("candidate_id", "")
            name = item.get("name", "")
            summary = item.get("summary", "")
            lines.append(f"- candidate_id: {candidate_id}")
            lines.append(f"  name: {name}")
            lines.append(f"  summary: {summary}")
        return "\n".join(lines).strip()

    @staticmethod
    def _build_runtime_info_block(runtime_info: Optional[Dict[str, Any]]) -> str:
        if not runtime_info:
            return ""

        lines = ["## 运行时信息"]
        for key, value in runtime_info.items():
            if key.startswith("_"):
                continue
            lines.append(f"- {key}: {value}")
        return "\n".join(lines).strip()

