"""阶段 4：RAG 问答、SSE 流式、引用溯源与会话历史测试。"""

import json
from collections.abc import AsyncIterator
from pathlib import Path

from app.api.chat import _stream_tokens
from app.services import rag
from app.services.llm import LLMUnavailableError, MockLLMProvider, get_llm
from httpx import AsyncClient

SAMPLE_DIR = Path(__file__).resolve().parent.parent / "docs"

ASK_URL = "/api/chat/ask"
HISTORY_URL = "/api/chat/history"


async def _collect_sse(
    client: AsyncClient,
    payload: dict,
    headers: dict[str, str],
) -> list[tuple[str, dict]]:
    """读取 SSE 流并解析为 (event, data) 列表。"""
    events: list[tuple[str, dict]] = []
    async with client.stream("POST", ASK_URL, json=payload, headers=headers) as response:
        assert response.status_code == 200, await response.aread()
        assert response.headers["content-type"].startswith("text/event-stream")
        event_name = "message"
        async for line in response.aiter_lines():
            if not line:
                continue
            if line.startswith("event:"):
                event_name = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                raw = line.split(":", 1)[1].strip()
                events.append((event_name, json.loads(raw)))
    return events


def _joined(events: list[tuple[str, dict]]) -> str:
    """把所有 message 事件的 delta 拼成完整回答。"""
    return "".join(data.get("delta", "") for name, data in events if name == "message")


async def _prepare_kb_with_doc(
    client: AsyncClient, headers: dict[str, str], name: str = "问答库"
) -> dict:
    """创建知识库并上传 sample.md。"""
    kb_resp = await client.post("/api/kb", json={"name": name}, headers=headers)
    assert kb_resp.status_code == 201, kb_resp.text
    kb = kb_resp.json()

    upload = await client.post(
        "/api/docs/upload",
        files={"file": ("sample.md", (SAMPLE_DIR / "sample.md").read_bytes(), "text/markdown")},
        data={"kb_id": str(kb["id"])},
        headers=headers,
    )
    assert upload.status_code == 201, upload.text
    assert upload.json()["status"] == "ready"
    return kb


async def test_ask_streams_answer_with_citations(client: AsyncClient, tenant_admin: dict) -> None:
    """正常路径：SSE 逐段输出，done 事件带引用，消息落库。"""
    kb = await _prepare_kb_with_doc(client, tenant_admin["headers"])

    events = await _collect_sse(
        client,
        {"kb_id": kb["id"], "question": "报销流程是什么？"},
        tenant_admin["headers"],
    )

    assert events, "SSE 事件不能为空"
    assert events[-1][0] == "done"

    answer = _joined(events)
    assert answer
    assert "mock" in answer

    done = events[-1][1]
    assert done["conversation_id"] > 0
    assert done["message_id"] > 0
    assert done["content_length"] == len(answer)
    assert done["citations"], "回答必须带引用"
    first = done["citations"][0]
    assert first["filename"] == "sample.md"
    assert first["document_title"] == "sample.md"
    assert first["score"] > 0
    assert first["snippet"]

    history = await client.get(HISTORY_URL, headers=tenant_admin["headers"])
    assert history.status_code == 200
    body = history.json()
    assert body["total"] == 1
    assert body["items"][0]["message_count"] == 2
    assert body["items"][0]["id"] == done["conversation_id"]

    detail = await client.get(
        f"{HISTORY_URL}/{done['conversation_id']}", headers=tenant_admin["headers"]
    )
    assert detail.status_code == 200
    messages = detail.json()["messages"]
    assert [message["role"] for message in messages] == ["user", "assistant"]
    assert messages[0]["content"] == "报销流程是什么？"
    assert messages[1]["content"] == answer
    assert messages[1]["citations"][0]["chunk_id"] == first["chunk_id"]


async def test_ask_with_empty_kb(client: AsyncClient, tenant_admin: dict) -> None:
    """空知识库：仍正常回答，但引用为空并说明无资料。"""
    kb_resp = await client.post(
        "/api/kb", json={"name": "空问答库"}, headers=tenant_admin["headers"]
    )
    kb = kb_resp.json()

    events = await _collect_sse(
        client,
        {"kb_id": kb["id"], "question": "报销流程是什么？"},
        tenant_admin["headers"],
    )

    answer = _joined(events)
    assert events[-1][0] == "done"
    assert events[-1][1]["citations"] == []
    assert "没有检索到" in answer


async def test_conversation_continuity(client: AsyncClient, tenant_admin: dict) -> None:
    """续聊：传 conversation_id 时消息追加到同一会话。"""
    kb = await _prepare_kb_with_doc(client, tenant_admin["headers"], name="续聊库")

    first = await _collect_sse(
        client, {"kb_id": kb["id"], "question": "报销流程是什么？"}, tenant_admin["headers"]
    )
    conversation_id = first[-1][1]["conversation_id"]

    second = await _collect_sse(
        client,
        {"kb_id": kb["id"], "question": "住宿标准是多少？", "conversation_id": conversation_id},
        tenant_admin["headers"],
    )
    assert second[-1][1]["conversation_id"] == conversation_id

    detail = await client.get(f"{HISTORY_URL}/{conversation_id}", headers=tenant_admin["headers"])
    assert detail.json()["conversation"]["message_count"] == 4
    roles = [message["role"] for message in detail.json()["messages"]]
    assert roles == ["user", "assistant", "user", "assistant"]


async def test_conversation_kb_mismatch(client: AsyncClient, tenant_admin: dict) -> None:
    """异常路径：续聊时知识库不一致返回 400。"""
    kb_a = await _prepare_kb_with_doc(client, tenant_admin["headers"], name="库A")
    kb_b_resp = await client.post("/api/kb", json={"name": "库B"}, headers=tenant_admin["headers"])
    kb_b = kb_b_resp.json()

    first = await _collect_sse(
        client, {"kb_id": kb_a["id"], "question": "报销流程？"}, tenant_admin["headers"]
    )
    conversation_id = first[-1][1]["conversation_id"]

    resp = await client.post(
        ASK_URL,
        json={"kb_id": kb_b["id"], "question": "继续", "conversation_id": conversation_id},
        headers=tenant_admin["headers"],
    )

    assert resp.status_code == 400
    assert resp.json()["code"] == 40001


async def test_conversation_not_found(client: AsyncClient, tenant_admin: dict) -> None:
    """异常路径：不存在的会话返回 404。"""
    kb = await _prepare_kb_with_doc(client, tenant_admin["headers"], name="会话库")

    resp = await client.post(
        ASK_URL,
        json={"kb_id": kb["id"], "question": "报销流程？", "conversation_id": 999999},
        headers=tenant_admin["headers"],
    )

    assert resp.status_code == 404
    assert resp.json()["code"] == 40401


async def test_ask_unknown_kb(client: AsyncClient, tenant_admin: dict) -> None:
    """异常路径：知识库不存在返回 404（JSON 错误，而非 SSE）。"""
    resp = await client.post(
        ASK_URL,
        json={"kb_id": 999999, "question": "报销流程？"},
        headers=tenant_admin["headers"],
    )

    assert resp.status_code == 404
    assert resp.json()["code"] == 40401


async def test_ask_validation(client: AsyncClient, tenant_admin: dict) -> None:
    """异常路径：空问题返回 40001。"""
    kb = await _prepare_kb_with_doc(client, tenant_admin["headers"], name="校验库")

    resp = await client.post(
        ASK_URL, json={"kb_id": kb["id"], "question": ""}, headers=tenant_admin["headers"]
    )

    assert resp.status_code == 422
    assert resp.json()["code"] == 40001


async def test_ask_requires_auth(client: AsyncClient) -> None:
    """异常路径：未携带令牌返回 401。"""
    resp = await client.post(ASK_URL, json={"kb_id": 1, "question": "你号"})

    assert resp.status_code == 401
    assert resp.json()["code"] == 40101


async def test_history_isolated_between_users(
    client: AsyncClient, tenant_admin: dict, member_headers: dict
) -> None:
    """多用户隔离：member 看不到 admin 的会话。"""
    kb = await _prepare_kb_with_doc(client, tenant_admin["headers"], name="隔离库")
    admin_events = await _collect_sse(
        client, {"kb_id": kb["id"], "question": "报销流程？"}, tenant_admin["headers"]
    )
    conversation_id = admin_events[-1][1]["conversation_id"]

    member_history = await client.get(HISTORY_URL, headers=member_headers)
    assert member_history.status_code == 200
    assert member_history.json()["total"] == 0

    member_detail = await client.get(f"{HISTORY_URL}/{conversation_id}", headers=member_headers)
    assert member_detail.status_code == 404

    admin_history = await client.get(HISTORY_URL, headers=tenant_admin["headers"])
    assert admin_history.json()["total"] == 1


async def test_history_isolated_between_tenants(client: AsyncClient, tenant_admin: dict) -> None:
    """多租户隔离：其它租户看不到本租户会话。"""
    kb = await _prepare_kb_with_doc(client, tenant_admin["headers"], name="租户库")
    await _collect_sse(
        client, {"kb_id": kb["id"], "question": "报销流程？"}, tenant_admin["headers"]
    )

    other = await client.post(
        "/api/auth/register",
        json={
            "tenant_name": "Tenant B",
            "tenant_slug": "tenant-b",
            "username": "admin",
            "email": "b@example.com",
            "password": "secret123",
        },
    )
    other_headers = {"Authorization": f"Bearer {other.json()['access_token']}"}

    resp = await client.get(HISTORY_URL, headers=other_headers)
    assert resp.status_code == 200
    assert resp.json()["total"] == 0


async def test_citations_match_hits() -> None:
    """引用编号从 1 开始，与检索命中一一对应。"""
    from app.schemas.search import SearchHit

    hits = [
        SearchHit(
            chunk_id=11,
            document_id=2,
            document_title="sample.md",
            filename="sample.md",
            chunk_index=0,
            content="报销流程说明",
            score=0.229,
        ),
        SearchHit(
            chunk_id=12,
            document_id=3,
            document_title="sample.txt",
            filename="sample.txt",
            chunk_index=0,
            content="员工手册",
            score=0.0,
        ),
    ]

    citations = rag.build_citations(hits)

    assert [item["index"] for item in citations] == [1, 2]
    assert citations[0]["chunk_id"] == 11
    assert citations[1]["filename"] == "sample.txt"
    assert citations[0]["snippet"] == "报销流程说明"


def test_prompt_contains_context_and_question() -> None:
    """Prompt 同时包含编号资料与问题，并要求引用。"""
    from app.schemas.search import SearchHit

    hits = [
        SearchHit(
            chunk_id=1,
            document_id=1,
            document_title="a.md",
            filename="a.md",
            chunk_index=0,
            content="报销需要主管审批",
            score=0.5,
        )
    ]

    messages = rag.build_messages("报销流程是什么？", hits)

    assert messages[0]["role"] == "system"
    assert "禁止编造" in messages[0]["content"]
    user_prompt = messages[1]["content"]
    assert "[1] 来源：a.md" in user_prompt
    assert "报销需要主管审批" in user_prompt
    assert "【问题】" in user_prompt
    assert "报销流程是什么？" in user_prompt


async def test_mock_llm_echoes_context() -> None:
    """mock 模型离线回显资料片段，且不依赖网络。"""
    from app.schemas.search import SearchHit

    hits = [
        SearchHit(
            chunk_id=1,
            document_id=1,
            document_title="a.md",
            filename="a.md",
            chunk_index=0,
            content="报销流程：提交、主管审批、财务审核、出纳付款。",
            score=0.4,
        )
    ]
    messages = rag.build_messages("报销流程是什么？", hits)

    pieces = [piece async for piece in MockLLMProvider().stream_chat(messages)]
    answer = "".join(pieces)

    assert "报销流程" in answer
    assert "[1]" in answer
    assert "mock" in answer


async def test_stream_falls_back_to_mock_on_unavailable() -> None:
    """模型在首个 token 前不可用时自动降级为 mock。"""

    class BrokenProvider:
        name = "openai_compatible"

        async def stream_chat(self, messages: list[dict[str, str]]) -> AsyncIterator[str]:
            raise LLMUnavailableError("429 too many requests")
            yield ""  # pragma: no cover - 仅用于标记异步生成器

    messages = [{"role": "user", "content": "【资料】\n（无检索结果）\n\n【问题】\n报销流程？"}]

    pieces = [piece async for piece in _stream_tokens(BrokenProvider(), messages)]

    assert "mock" in "".join(pieces)


def test_get_llm_defaults_to_mock() -> None:
    """默认配置返回 mock Provider。"""
    assert get_llm().name == "mock"
