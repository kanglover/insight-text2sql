"""Prompt 模板集中管理。

把 Prompt 从节点代码里抽出来，一是方便对比调优，二是方便在测试里断言
「关键约束有没有真的写进 Prompt」（例如禁止 SELECT *、禁止编造字段）。
"""

import json
from typing import Any

SQL_SYSTEM_PROMPT = """你是一名资深数据仓库 SQL 工程师，负责把业务人员的自然语言问题翻译成可直接执行的查询 SQL。

必须遵守的规则：
1. 只能使用「可用表结构」中出现的表和字段，禁止编造任何表名或字段名。
2. 只输出一条 SELECT 查询语句，不要输出解释、不要输出 markdown 代码块、不要输出分号结尾的多语句。
3. 每个投影列都必须用双引号中文别名，例如 SUM(r.revenue) AS "收入额"，这样业务同学能直接看懂表头。
4. 不允许使用 SELECT *，必须显式列出需要的字段。
5. 字符串常量用单引号，例如 '数字政府'。
6. 不同事实表的统计粒度可能不同（例如收入按天、目标按产品线）。跨表关联时必须先各自聚合再 JOIN，避免 JOIN 造成的行膨胀让指标被重复放大。
7. 对聚合结果的过滤条件（例如「收入在 3000 万到 5000 万之间」）要用 HAVING，不要用 WHERE。
8. 比率类指标保留 1 位小数，使用 ROUND(x, 1)，并注意除零（用 NULLIF 或 CASE）。
9. 排序类问题要给出 ORDER BY 和合理的 LIMIT。默认统计年份取「当前年份」，除非用户明确指定。
10. 单位统一是「万元」，不要做单位换算。

只返回 SQL。"""

ANSWER_SYSTEM_PROMPT = """你是一名企业经营分析助手。根据给定的用户问题和 SQL 查询结果，输出简洁、专业的中文分析结论。

要求：
1. 先用一句话给出结论，再分点列出关键数据（最多 5 条），数值保留 1 位小数并带上单位「万元」或「%」。
2. 只能引用查询结果里真实存在的数字，不要编造、不要外推。
3. 如果结果为空，直接说明「未查询到符合条件的数据」，并给出可能的原因或建议的调整方向。
4. 不要输出 SQL，不要输出 markdown 标题，纯文本即可，可以使用「1. 2. 3.」这样的序号。"""


def build_sql_prompt(
    query: str,
    tables: list[dict[str, Any]],
    metrics: list[dict[str, Any]],
    values: list[dict[str, Any]],
    date_info: dict[str, str],
    db_info: dict[str, str],
    examples: list[dict[str, Any]],
    join_paths: list[str] | None = None,
) -> str:
    """拼装 SQL 生成的 user prompt。"""

    def dump(payload: Any) -> str:
        return json.dumps(payload, ensure_ascii=False, indent=2)

    sections: list[str] = []

    sections.append(
        "【可用表结构】\n"
        + "\n".join(
            f"- {t['name']}（{t.get('comment', '')}，{t.get('role', '')} 表）\n"
            + "  字段："
            + "；".join(
                f"{c['name']} {c['type']} {c['comment']}（{c['role']}）" for c in t["columns"]
            )
            for t in tables
        )
    )

    if join_paths:
        sections.append(
            "【可用连接路径（多表查询请只使用这些 join 条件）】\n"
            + "\n".join(f"- {p}" for p in join_paths)
        )

    if metrics:
        sections.append(
            "【业务指标口径】\n"
            + "\n".join(
                f"- {m['name']}：{m.get('description', '')}；口径 {m.get('formula', '')}；单位 {m.get('unit', '')}"
                for m in metrics
            )
        )

    if values:
        sections.append(
            "【字段真实取值（必须使用这里的原文，不要改写）】\n"
            + "\n".join(
                f"- {v['table']}.{v['column']} = '{v['value']}'"
                + (f"（{v['desc']}）" if v.get("desc") else "")
                for v in values
            )
        )

    sections.append(
        "【运行环境】\n"
        f"数据库方言：{db_info.get('dialect', 'sqlite')}；版本：{db_info.get('version', '')}\n"
        f"当前日期：{date_info.get('date', '')}（{date_info.get('weekday', '')}，{date_info.get('quarter', '')}）"
    )

    if examples:
        sections.append(
            "【参考范例（问题 → SQL）】\n"
            + "\n\n".join(f"问题：{e['question']}\nSQL：\n{e['sql']}" for e in examples)
        )

    sections.append(f"【用户问题】\n{query}")
    sections.append("请只返回 SQL。")
    return "\n\n".join(sections)


def build_answer_prompt(query: str, sql: str, columns: list[str], rows: list[list[Any]]) -> str:
    preview = [dict(zip(columns, row, strict=False)) for row in rows[:50]]
    return (
        f"【用户问题】\n{query}\n\n"
        f"【执行的 SQL】\n{sql}\n\n"
        f"【查询结果（共 {len(rows)} 行，最多预览 50 行）】\n"
        f"{json.dumps(preview, ensure_ascii=False, indent=2, default=str)}\n\n"
        "请给出分析结论。"
    )


def build_feedback_prompt(
    first_prompt: str, failed_sql: str, error: str, dialect: str = "sqlite"
) -> str:
    return (
        f"{first_prompt}\n\n"
        f"【上一版 SQL（执行失败）】\n{failed_sql}\n\n"
        f"【{dialect} 报错信息】\n{error}\n\n"
        "请修正上述错误，重新输出一条完整可执行的 SQL。只返回 SQL。"
    )
