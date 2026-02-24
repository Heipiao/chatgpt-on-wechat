"""
Resume Search tool - Search and manage candidate resumes via the Resume Search HTTP service.
Calls POST /search, GET /resume/{candidate_id}, POST /update.
Base URL: RESUME_SEARCH_BASE_URL or http://121.199.74.224:8000
"""

import os
from typing import Dict, Any, Optional

import requests

from agent.tools.base_tool import BaseTool, ToolResult
from common.log import logger


DEFAULT_BASE_URL = "http://121.199.74.224:8000"
DEFAULT_TIMEOUT = 30


class ResumeSearch(BaseTool):
    """Tool for searching resumes, getting one resume by id, or updating resume fields."""

    name: str = "resume_search"
    description: str = (
        "Search candidate resumes, get a resume by candidate_id, or update resume fields. "
        "Use when the user asks to search candidates, filter by keywords/conditions, "
        "view a specific resume, or update candidate information."
    )

    params: dict = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["search", "get", "update"],
                "description": "search: search resumes by query and filters; get: get one resume by candidate_id; update: update resume fields"
            },
            "query": {
                "type": "string",
                "description": "Search keywords (for action=search)"
            },
            "filters": {
                "type": "object",
                "description": "Filter conditions, e.g. {\"location_city\": \"北京\", \"years_of_experience\": {\"gte\": 5}} (for action=search)"
            },
            "size": {
                "type": "integer",
                "description": "Number of results to return (1-200, default 10) (for action=search)"
            },
            "from_": {
                "type": "integer",
                "description": "Offset for pagination (default 0) (for action=search)"
            },
            "include_fields": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Only return these fields in search results (for action=search)"
            },
            "candidate_id": {
                "type": "string",
                "description": "Candidate ID (required for action=get and action=update)"
            },
            "fields": {
                "type": "object",
                "description": "Fields to update, e.g. {\"summary\": \"...\"} (for action=update)"
            },
            "upsert": {
                "type": "boolean",
                "description": "If true, create resume when not found (for action=update, default false)"
            }
        },
        "required": ["action"]
    }

    def __init__(self, config: dict = None):
        self.config = config or {}
        self._base_url = (
            os.environ.get("RESUME_SEARCH_BASE_URL")
            or self.config.get("base_url")
            or DEFAULT_BASE_URL
        ).rstrip("/")

    def _request(self, method: str, path: str, **kwargs) -> requests.Response:
        url = f"{self._base_url}{path}"
        return requests.request(method, url, timeout=DEFAULT_TIMEOUT, **kwargs)

    def execute(self, args: Dict[str, Any]) -> ToolResult:
        action = (args.get("action") or "").strip().lower()
        if not action:
            return ToolResult.fail("Error: 'action' is required (search, get, or update)")

        try:
            if action == "search":
                return self._do_search(args)
            if action == "get":
                return self._do_get(args)
            if action == "update":
                return self._do_update(args)
            return ToolResult.fail(f"Error: unknown action '{action}'. Use search, get, or update.")
        except requests.Timeout:
            return ToolResult.fail(f"Error: Request timed out after {DEFAULT_TIMEOUT}s")
        except requests.ConnectionError:
            return ToolResult.fail(f"Error: Cannot connect to resume service at {self._base_url}")
        except Exception as e:
            logger.error(f"[ResumeSearch] Unexpected error: {e}", exc_info=True)
            return ToolResult.fail(f"Error: {str(e)}")

    # 搜索默认只返回这几项，避免整条简历过多；传 include_fields 则用传入的
    DEFAULT_SEARCH_FIELDS = ["candidate_id", "name_full", "core_summary", "extracted_tags"]

    def _do_search(self, args: Dict[str, Any]) -> ToolResult:
        payload = {}
        if args.get("query") is not None:
            payload["query"] = args["query"]
        if args.get("filters") is not None:
            payload["filters"] = args["filters"]
        if args.get("size") is not None:
            size = args["size"]
            if isinstance(size, int) and 1 <= size <= 200:
                payload["size"] = size
        if args.get("from_") is not None:
            from_ = args["from_"]
            if isinstance(from_, int) and from_ >= 0:
                payload["from_"] = from_
        payload["include_fields"] = args.get("include_fields") or self.DEFAULT_SEARCH_FIELDS

        resp = self._request("POST", "/search", json=payload)
        if resp.status_code != 200:
            return ToolResult.fail(f"Error: Resume search returned HTTP {resp.status_code}: {resp.text[:200]}")
        data = resp.json()
        return ToolResult.success(data)

    def _do_get(self, args: Dict[str, Any]) -> ToolResult:
        candidate_id = (args.get("candidate_id") or "").strip()
        if not candidate_id:
            return ToolResult.fail("Error: 'candidate_id' is required for action=get")
        resp = self._request("GET", f"/resume/{candidate_id}")
        if resp.status_code == 404:
            return ToolResult.fail(f"Error: Resume not found for candidate_id={candidate_id}")
        if resp.status_code != 200:
            return ToolResult.fail(f"Error: Get resume returned HTTP {resp.status_code}: {resp.text[:200]}")
        return ToolResult.success(resp.json())

    def _do_update(self, args: Dict[str, Any]) -> ToolResult:
        candidate_id = (args.get("candidate_id") or "").strip()
        if not candidate_id:
            return ToolResult.fail("Error: 'candidate_id' is required for action=update")
        fields = args.get("fields")
        if not isinstance(fields, dict):
            return ToolResult.fail("Error: 'fields' must be an object for action=update")
        payload = {
            "candidate_id": candidate_id,
            "fields": fields,
            "upsert": bool(args.get("upsert", False)),
        }
        resp = self._request("POST", "/update", json=payload)
        if resp.status_code == 404:
            return ToolResult.fail(f"Error: Resume not found for candidate_id={candidate_id} (set upsert=true to create)")
        if resp.status_code != 200:
            return ToolResult.fail(f"Error: Update returned HTTP {resp.status_code}: {resp.text[:200]}")

        name = fields.get("name_full") or candidate_id
        card = self._build_update_card(name, fields)
        return ToolResult.success({
            "type": "feishu_card",
            "title": f"简历已更新 - {name}",
            "card": card,
            "update_result": resp.json(),
        })

    @staticmethod
    def _build_update_card(name: str, fields: Dict[str, Any]) -> dict:
        elements = []
        for key, value in fields.items():
            elements.append({
                "tag": "div",
                "text": {"tag": "lark_md", "content": f"**{key}**: {value}"},
            })
        return {
            "header": {
                "title": {"tag": "plain_text", "content": f"简历已更新 - {name}"},
                "template": "blue",
            },
            "elements": elements,
        }
