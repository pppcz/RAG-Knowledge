"""RAG Prompt 组装与引用溯源。"""

from app.schemas.search import SearchHit

SYSTEM_PROMPT = (
    "你是企业知识库问答助手。必须严格依据用户提供的【资料】回答，禁止编造资料之外的信息。\n"
    "要求：\n"
    "1. 用中文回答，条理清晰，必要时使用列表；\n"
    "2. 每条关键结论后用 [编号] 标注引用的资料，例如 [1]；\n"
    "3. 如果资料不足以回答，直接说明「根据现有资料无法确定」，并指出缺少什么；\n"
    "4. 不要输出资料中没有的数字、日期或结论。"
)


def build_citations(hits: list[SearchHit]) -> list[dict]:
    """检索结果 → 引用列表（文档名、片段、相似度）。"""
    citations: list[dict] = []
    for index, hit in enumerate(hits, start=1):
        citations.append(
            {
                "index": index,
                "document_id": hit.document_id,
                "document_title": hit.document_title,
                "filename": hit.filename,
                "chunk_id": hit.chunk_id,
                "chunk_index": hit.chunk_index,
                "score": hit.score,
                "snippet": " ".join(hit.content.split())[:200],
            }
        )
    return citations


def build_user_prompt(question: str, hits: list[SearchHit]) -> str:
    """拼装 user 消息：编号资料 + 问题。"""
    if not hits:
        context = "（无检索结果）"
    else:
        blocks = []
        for index, hit in enumerate(hits, start=1):
            blocks.append(
                f"[{index}] 来源：{hit.filename}｜相似度 {hit.score:.3f}｜片段 {hit.chunk_index}\n"
                f"{hit.content.strip()}"
            )
        context = "\n\n".join(blocks)

    return f"【资料】\n{context}\n\n【问题】\n{question.strip()}"


def build_messages(question: str, hits: list[SearchHit]) -> list[dict[str, str]]:
    """组装 system + user 消息。"""
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": build_user_prompt(question, hits)},
    ]
