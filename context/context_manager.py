import os
from typing import Any, Dict, List, Optional

from context.recent_resume import ResumeContextService
from context.utils import SystemMarkdownLoader
from common.log import logger

# 与 agent_stream 一致的截断上限，便于 tool/消息 管理一致
# agent_stream: 当前轮 tool result 50000 字，历史轮 20000 字
MAX_CURRENT_TURN_RESULT_CHARS = 50000
MAX_HISTORY_RESULT_CHARS = 20000
# 最近简历块总长上限，避免 system 过长
MAX_RECENT_RESUME_BLOCK_CHARS = 15000
# 单条 summary 展示上限
MAX_SINGLE_SUMMARY_CHARS = 2000


class ContextManager:
    """
    Core context orchestrator.

    Responsibilities:
    - Build system prompt: 与线上一致时可传入 base_prompt（与 Agent/PromptBuilder 一致）
    - Default 使用 context/data/system_prompt.md；传入 base_prompt 时以线上 base 为准
    - 注入最近浏览简历摘要块（带截断，与 tool 管理截断策略一致）
    - 运行时信息块格式与 agent/prompt/builder 的 _build_runtime_section 一致
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
        base_prompt: Optional[str] = None,
    ) -> str:
        """
        Build final system prompt，与线上（Agent/PromptBuilder）一致时可传 base_prompt。

        - base: 若传 base_prompt 则使用（与线上一致）；否则用 context/data/system_prompt.md
        - recent resume 块（带截断，与 agent_stream 的 tool 截断策略一致）
        - runtime 块格式与 agent/prompt/builder 的 _build_runtime_section 一致
        """
        if base_prompt is not None and (base_prompt.strip()):
            base = base_prompt.strip()
        else:
            base = (self.system_loader.read() or "").strip()
        blocks: List[str] = [base] if base else []

        block_limit = recent_limit if recent_limit is not None else self.recent_resume_limit
        recent_block = self._build_recent_resume_block(session_id=session_id, limit=block_limit)
        if recent_block:
            blocks.append(recent_block)

        runtime_block = self._build_runtime_info_block(runtime_info)
        if runtime_block:
            blocks.append(runtime_block)

        result = "\n\n".join(blocks).strip()
        logger.info(
            "[ContextManager] build_system_prompt: session_id=%s, base_len=%s, recent_block=%s, runtime_block=%s, total_len=%s",
            session_id or "(empty)",
            len(base),
            "yes" if recent_block else "no",
            "yes" if runtime_block else "no",
            len(result),
        )
        return result

    def build_payload(
        self,
        session_id: str,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        runtime_info: Optional[Dict[str, Any]] = None,
        base_prompt: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Build model payload. 与线上一致时传入 base_prompt（与 Agent/PromptBuilder 一致）。

        Note:
        - messages/tools 的截断由上游 agent_stream 负责（MAX_CURRENT_TURN_RESULT_CHARS / MAX_HISTORY_RESULT_CHARS）
        - 本类不改变 message 顺序或 trim 行为
        """
        system_prompt = self.build_system_prompt(
            session_id=session_id,
            runtime_info=runtime_info,
            base_prompt=base_prompt,
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
        total = 0
        for item in items:
            if total >= MAX_RECENT_RESUME_BLOCK_CHARS:
                lines.append("- [已截断: 最近简历块已达长度上限]")
                break
            candidate_id = (item.get("candidate_id") or "").strip()
            name = (item.get("name") or "").strip()
            summary = (item.get("summary") or "").strip()
            if len(summary) > MAX_SINGLE_SUMMARY_CHARS:
                summary = summary[:MAX_SINGLE_SUMMARY_CHARS] + f"… [已截断，总长 {len(item.get('summary', ''))} 字]"
            line_candidate = f"- candidate_id: {candidate_id}"
            line_name = f"  name: {name}"
            line_summary = f"  summary: {summary}"
            block_size = len(line_candidate) + len(line_name) + len(line_summary) + 3
            if total + block_size > MAX_RECENT_RESUME_BLOCK_CHARS:
                lines.append("- [已截断: 最近简历块已达长度上限]")
                break
            lines.append(line_candidate)
            lines.append(line_name)
            lines.append(line_summary)
            total += block_size
        return "\n".join(lines).strip()

    @staticmethod
    def _build_runtime_info_block(runtime_info: Optional[Dict[str, Any]]) -> str:
        """与 agent/prompt/builder._build_runtime_section 格式一致，支持 _get_current_time 动态时间。"""
        if not runtime_info:
            return ""

        lines = ["## 运行时信息", ""]
        if callable(runtime_info.get("_get_current_time")):
            try:
                time_info = runtime_info["_get_current_time"]()
                time_line = f"当前时间: {time_info['time']} {time_info['weekday']} ({time_info['timezone']})"
                lines.append(time_line)
                lines.append("")
            except Exception:
                pass
        elif runtime_info.get("current_time"):
            time_str = runtime_info["current_time"]
            weekday = runtime_info.get("weekday", "")
            timezone = runtime_info.get("timezone", "")
            time_line = f"当前时间: {time_str}"
            if weekday:
                time_line += f" {weekday}"
            if timezone:
                time_line += f" ({timezone})"
            lines.append(time_line)
            lines.append("")

        runtime_parts = []
        if runtime_info.get("model"):
            runtime_parts.append(f"模型={runtime_info['model']}")
        if runtime_info.get("workspace"):
            runtime_parts.append(f"工作空间={runtime_info['workspace']}")
        if runtime_info.get("channel") and runtime_info.get("channel") != "web":
            runtime_parts.append(f"渠道={runtime_info['channel']}")
        if runtime_parts:
            lines.append("运行时: " + " | ".join(runtime_parts))
            lines.append("")

        return "\n".join(lines).strip()

