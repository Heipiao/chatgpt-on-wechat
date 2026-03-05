"""
Test the four resume_search actions: search (DSL), get, update, delete.
Run from project root (chatgpt-on-wechat):
  python -m agent.tools.resume_search.test_resume_search
  or: pytest agent/tools/resume_search/test_resume_search.py -v

If curl works but this test times out: run the test in your system terminal
(same environment where curl runs). IDE/sandbox may block outbound network.
"""

import os
import sys

import requests

TEST_TIMEOUT = 15


def test_resume_search_four_actions():
    """Test search (DSL) -> get -> update -> (skip delete) in sequence."""
    _here = os.path.abspath(__file__)
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(_here))))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    from agent.tools.resume_search.resume_search import ResumeSearch
    from agent.tools.base_tool import ToolResult

    tool = ResumeSearch()
    base_url = tool._base_url
    print(f"Base URL: {base_url}\n")

    try:
        r = requests.get(f"{base_url}/health", timeout=TEST_TIMEOUT)
        r.raise_for_status()
        print(f"Health check OK: {r.json()}\n")
    except (requests.Timeout, requests.ConnectionError) as e:
        print(
            "Resume service not reachable from this process (timeout or connection error).\n"
            "If curl works in your terminal, run this test in the same terminal:\n"
            "  cd chatgpt-on-wechat && python -m agent.tools.resume_search.test_resume_search\n"
            f"Error: {e}"
        )
        raise

    # ---- 1. search (DSL) ----
    print("1. Testing action=search (DSL) ...")
    res = tool.execute({
        "action": "search",
        "dsl": {
            "query": {
                "multi_match": {
                    "query": "产品",
                    "fields": ["name_full^3", "current_title^3", "core_summary^2", "doc_text_clean"],
                    "analyzer": "ik_smart",
                }
            },
            "size": 2,
            "from": 0,
            "highlight": {
                "fields": {"core_summary": {}, "current_title": {}}
            },
        },
    })
    assert isinstance(res, ToolResult), "search should return ToolResult"
    assert res.status == "success", f"search failed: {res.result}"
    data = res.result
    if data.get("type") == "feishu_card":
        data = data["search_result"]
    assert "total" in data and "hits" in data, f"search result should have total and hits: {data}"
    print(f"   total={data['total']}, hits={len(data['hits'])}")
    if data["hits"]:
        print(f"   first candidate_id={data['hits'][0].get('candidate_id')}")
    print("   search OK\n")

    # ---- 2. get ----
    candidate_id = None
    if data.get("hits"):
        candidate_id = data["hits"][0].get("candidate_id")
    if not candidate_id:
        print("2. Skipping get (no candidate_id from search)\n")
    else:
        print("2. Testing action=get ...")
        res = tool.execute({"action": "get", "candidate_id": candidate_id})
        assert isinstance(res, ToolResult), "get should return ToolResult"
        assert res.status == "success", f"get failed: {res.result}"
        doc = res.result
        assert isinstance(doc, dict), f"get result should be dict: {doc}"
        print(f"   candidate_id={doc.get('candidate_id')}, name_full={doc.get('name_full')}")
        print("   get OK\n")

    # ---- 3. update ----
    if not candidate_id:
        print("3. Skipping update (no candidate_id)\n")
        print("4. Skipping delete (no candidate_id)\n")
        return

    print("3. Testing action=update ...")
    res = tool.execute({
        "action": "update",
        "candidate_id": candidate_id,
        "fields": {"notes_internal": "test_resume_search.py run"},
    })
    assert isinstance(res, ToolResult), "update should return ToolResult"
    assert res.status == "success", f"update failed: {res.result}"
    out = res.result
    if out.get("type") == "feishu_card":
        out = out["update_result"]
    assert isinstance(out, dict) and out.get("result") == "updated", f"update result: {out}"
    print(f"   result={out.get('result')}, updated_fields={out.get('updated_fields')}")
    print("   update OK\n")

    # ---- 4. delete (skip actual deletion to avoid data loss) ----
    print("4. Skipping delete action in test to avoid data loss.")
    print("   (delete action is implemented and callable via action='delete')\n")

    print("All actions passed.")


if __name__ == "__main__":
    test_resume_search_four_actions()
