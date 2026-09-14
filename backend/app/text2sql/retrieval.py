"""三类召回 + 上下文合并 + 表过滤。

对应流水线的前半段：
    recall_column / recall_metric / recall_value  →  merge_context  →  filter_tables

为什么要有「取值召回」这一路？
    用户问「上海代表处的收入」，如果只把字段名喂给模型，模型很可能写出
    `org_name = '上海分公司'` 这种并不存在的值，查出来是空的。
    取值召回负责把「上海代表处」这个真实枚举值连同所属字段一起交给模型。
"""

from dataclasses import dataclass, field

from app.core.config import settings
from app.entities import (
    ColumnInfo,
    MetaSnapshot,
    MetricInfo,
    TableInfo,
    ValueInfo,
)
from app.utils.text import idf, is_number_token, query_terms


@dataclass
class ScoredColumn:
    column: ColumnInfo
    score: float
    reasons: list[str] = field(default_factory=list)


@dataclass
class ScoredMetric:
    metric: MetricInfo
    score: float
    reasons: list[str] = field(default_factory=list)


@dataclass
class ScoredValue:
    value: ValueInfo
    score: float
    matched: str = ""


@dataclass
class RetrievalResult:
    columns: list[ScoredColumn] = field(default_factory=list)
    metrics: list[ScoredMetric] = field(default_factory=list)
    values: list[ScoredValue] = field(default_factory=list)
    terms: list[str] = field(default_factory=list)


def _doc_text(*parts: str) -> str:
    return " | ".join(p for p in parts if p).lower()


def _match_score(term: str, doc: str, weight: float) -> float:
    """一个查询词命中一个文档时的得分。"""
    if not term:
        return 0.0
    if term == doc:
        return 4.0 * weight
    if len(term) >= 2 and term in doc:
        return 2.5 * weight
    if term.isascii() and term in doc.split():
        return 2.0 * weight
    return 0.0


def recall_columns(
    query: str, keywords: list[str], snapshot: MetaSnapshot, top_k: int | None = None
) -> list[ScoredColumn]:
    top_k = top_k or settings.recall_top_k
    terms = query_terms(query, keywords)
    if not terms:
        return []

    # 「字段」才是本路召回的文档单元，IDF 必须在字段语料上统计。
    # 若按表统计，「金额」「时间」这类词会因为在表注释里少见而被误判为高区分度词。
    table_doc: dict[str, str] = {
        t.table_name: _doc_text(t.table_name, t.comment, t.business_domain) for t in snapshot.tables
    }
    column_docs: list[tuple[ColumnInfo, str, str, str]] = []
    for table in snapshot.tables:
        for column in table.columns:
            own = _doc_text(column.column_name, " ".join(column.synonyms))
            full = _doc_text(column.column_name, column.comment, " ".join(column.synonyms), table.comment)
            column_docs.append((column, own, full, table_doc[table.table_name]))

    hits = {term: sum(1 for _, own, full, _ in column_docs if term in own or term in full) for term in terms}
    corpus_size = len(column_docs)
    priority = {t.table_name: t.priority for t in snapshot.tables}

    scored: list[ScoredColumn] = []
    for column, own, full, tdoc in column_docs:
        score = 0.0
        reasons: list[str] = []
        for term in terms:
            if not term:
                continue
            weight = idf(corpus_size, hits.get(term, 0))
            s = _match_score(term, own, 1.6) + _match_score(term, full, 1.0) * 0.6
            if s > 0:
                score += s * weight
                if term in own:
                    reasons.append(term)
            elif _match_score(term, tdoc, 1.0) > 0:
                score += 0.8 * weight
        if score <= 0:
            continue
        # 度量字段在问数里天然更常被用到，给一点先验
        if column.role == "measure":
            score *= 1.12
        # 主键/外键是「连接键」而不是「业务字段」：用户不会按 org_id 分组，
        # 它们只应该帮助把表带进候选集，不应该主导排序（否则每张带 org_id 的表都会挤进来）
        if column.role == "id":
            score *= 0.25
        score += priority.get(column.table_name, 0) / 1000.0
        scored.append(ScoredColumn(column=column, score=round(score, 4), reasons=reasons[:5]))

    scored.sort(key=lambda item: item.score, reverse=True)
    return scored[:top_k]


def recall_metrics(
    query: str, keywords: list[str], snapshot: MetaSnapshot, top_k: int | None = None
) -> list[ScoredMetric]:
    top_k = top_k or max(4, settings.recall_top_k // 2)
    terms = query_terms(query, keywords)
    if not terms:
        return []

    docs = [_doc_text(m.metric_name, " ".join(m.aliases), m.description) for m in snapshot.metrics]
    hits = {term: sum(1 for doc in docs if term in doc) for term in terms}

    scored: list[ScoredMetric] = []
    for metric in snapshot.metrics:
        name_doc = _doc_text(metric.metric_name, " ".join(metric.aliases))
        full_doc = _doc_text(metric.metric_name, " ".join(metric.aliases), metric.description)
        score = 0.0
        reasons: list[str] = []
        for term in terms:
            weight = idf(len(snapshot.metrics), hits.get(term, 0))
            s = _match_score(term, name_doc, 1.8) + _match_score(term, full_doc, 1.0) * 0.5
            if s > 0:
                score += s * weight
                reasons.append(term)
        if score > 0:
            scored.append(ScoredMetric(metric=metric, score=round(score, 4), reasons=reasons[:5]))

    scored.sort(key=lambda item: item.score, reverse=True)
    return scored[:top_k]


def recall_values(
    query: str, snapshot: MetaSnapshot, top_k: int | None = None
) -> list[ScoredValue]:
    """在问题里找真实存在的枚举值。这里必须精确，宁可召回不到，也不能召回错。"""
    top_k = top_k or max(6, settings.recall_top_k)
    text = (query or "").lower()
    scored: list[ScoredValue] = []
    for value in snapshot.values:
        candidates = [value.value, *value.synonyms]
        for cand in candidates:
            cand_low = cand.lower()
            if not cand_low:
                continue
            # 短值（<=1 字）容易误命中，不做子串匹配
            if len(cand_low) <= 1:
                continue
            if cand_low in text:
                scored.append(
                    ScoredValue(
                        value=value,
                        score=round(6.0 + len(cand_low) * 0.5, 4),
                        matched=cand,
                    )
                )
                break
            if is_number_token(cand_low) and cand_low in text:
                scored.append(ScoredValue(value=value, score=3.0, matched=cand))
                break
    scored.sort(key=lambda item: item.score, reverse=True)
    # 同一字段同一值只留一条
    seen: set[tuple[str, str, str]] = set()
    unique: list[ScoredValue] = []
    for item in scored:
        key = (item.value.table_name, item.value.column_name, item.value.value)
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique[:top_k]


def merge_context(
    retrieval: RetrievalResult, snapshot: MetaSnapshot, max_tables: int | None = None
) -> list[TableInfo]:
    """把三路召回的结果收敛成「候选表」列表。

    关键是保证「生成 SQL 真正需要的表」都在候选里：
    - 召回字段所在表；
    - 召回指标依赖的表（例如问题提到完成率，就必须带上目标表）；
    - 命中取值所在表。

    权重的直觉：指标依赖 > 字段 > 取值。
    指标是用户意图最直接的表达；取值只是过滤条件，带错表代价小。
    """
    max_tables = max_tables or settings.recall_max_tables
    table_score: dict[str, float] = {}

    for item in retrieval.columns:
        table_score[item.column.table_name] = table_score.get(item.column.table_name, 0) + item.score
    for item in retrieval.metrics:
        for qualified in item.metric.relevant_columns:
            table = qualified.split(".")[0]
            table_score[table] = table_score.get(table, 0) + item.score * 1.5
    for item in retrieval.values:
        table_score[item.value.table_name] = table_score.get(item.value.table_name, 0) + item.score * 0.5

    if not table_score:
        # 完全没召回时，给最核心的事实表兜底，保证流水线不至于空转
        table_score = {t.table_name: float(t.priority) for t in snapshot.tables if t.role == "fact"}

    # 相对阈值：只有靠通用连接键（org_id 这类）蹭进来的表会被滤掉，
    # 真正被问到的表分数会明显高于阈值。
    top = max(table_score.values())
    threshold = top * 0.30
    kept = {name: score for name, score in table_score.items() if score >= threshold}
    if len(kept) < 2:  # 至少保留两张表，否则连不成查询
        kept = dict(sorted(table_score.items(), key=lambda kv: kv[1], reverse=True)[:2])

    ranked = sorted(kept.items(), key=lambda kv: kv[1], reverse=True)[:max_tables]
    picked = [snapshot.table(name) for name, _ in ranked]
    return [t for t in picked if t is not None]


def build_table_context(tables: list[TableInfo]) -> list[dict]:
    """转成给 Prompt / 前端展示用的表结构上下文。"""
    context: list[dict] = []
    for table in tables:
        context.append(
            {
                "name": table.table_name,
                "comment": table.comment,
                "role": table.role,
                "columns": [
                    {
                        "name": c.column_name,
                        "type": c.data_type,
                        "comment": c.comment,
                        "role": c.role,
                    }
                    for c in table.columns
                ],
            }
        )
    return context
