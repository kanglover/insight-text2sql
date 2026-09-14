"""中文分词与文本工具。

不用额外引入向量模型：在「元数据只有几十张表、上百字段」这个量级上，
分词 + IDF 加权 + 子串命中的打分效果已经足够，而且完全可解释、可单测。
"""

import re

import jieba

# 只保留有业务信息量的词性：名词/地名/专名/英文/名动词/动词/形容词
ALLOW_POS = (
    "n",
    "nr",
    "ns",
    "nt",
    "nz",
    "eng",
    "vn",
    "v",
    "a",
    "an",
    "m",  # 数词，用于识别 TOP5 / 3000
)

# 这些都出现在几乎每句问数里，不承载区分度
STOPWORDS = {
    "的", "了", "和", "与", "及", "是", "在", "有", "对", "把", "被", "为", "给", "从", "到",
    "我", "你", "他", "我们", "你们", "请", "帮", "帮我", "一下", "看", "下", "吧", "呢", "吗",
    "多少", "哪些", "哪个", "什么", "怎么", "如何", "是否", "有没有", "以及", "分别", "情况",
    "数据", "信息", "统计", "查询", "查", "看", "展示", "显示", "给个", "来", "个", "条",
    "一下", "现在", "目前", "今年", "本年", "上年", "去年", "年", "月", "日", "季度", "几个",
}

_NUM_RE = re.compile(r"^\d+(\.\d+)?$")


def is_number_token(token: str) -> bool:
    return bool(_NUM_RE.match(token))


def tokenize(text: str) -> list[str]:
    """分词并过滤停用词，保留数字与英文缩写（G5、TOP5 这类）。"""
    tokens: list[str] = []
    for token in jieba.lcut(text or ""):
        token = token.strip().lower()
        if not token or token in STOPWORDS:
            continue
        if len(token) == 1 and not is_number_token(token) and not token.isascii():
            # 单字中文噪声太大，直接丢掉
            continue
        tokens.append(token)
    return tokens


def query_terms(text: str, extra: list[str] | None = None) -> list[str]:
    """返回去重后的查询词，附带原始问题里的连续中文片段（2-4 字），
    用于兜底捕捉「经营单元」这类容易被切开的长词。"""
    tokens = tokenize(text)
    grams: list[str] = []
    for seg in re.findall(r"[\u4e00-\u9fa5]{2,6}", text or ""):
        for size in (4, 3, 2):
            if len(seg) >= size:
                for i in range(len(seg) - size + 1):
                    grams.append(seg[i : i + size])
    for token in extra or []:
        tokens.extend(tokenize(token))

    seen: list[str] = []
    for token in [*tokens, *grams]:
        if token and token not in seen and token not in STOPWORDS:
            seen.append(token)
    return seen


def idf(doc_count: int, hit_count: int) -> float:
    """平滑 IDF：越少见的词权重越高。"""
    import math

    return math.log((doc_count + 1) / (hit_count + 1)) + 1.0
