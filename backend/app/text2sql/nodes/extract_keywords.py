"""① 抽取关键词。"""

import jieba.analyse

from app.text2sql.pipeline import Emit
from app.text2sql.state import PipelineContext, PipelineState
from app.utils.text import ALLOW_POS, tokenize


def extract(query: str) -> list[str]:
    """TF-IDF 关键词 + 分词结果 + 原始问题，三者合并去重。

    保留原始问题是兜底：即使分词切错，完整语义也不会丢。
    """
    tags = jieba.analyse.extract_tags(query, allowPOS=ALLOW_POS)
    ordered: list[str] = []
    for token in [*tags, *tokenize(query), query]:
        if token and token not in ordered:
            ordered.append(token)
    return ordered[:24]


async def extract_keywords(
    state: PipelineState, context: PipelineContext, emit: Emit
) -> dict:
    query = state.get("query", "")
    keywords = extract(query)
    emit({"type": "keywords", "keywords": keywords})
    return {"keywords": keywords}
