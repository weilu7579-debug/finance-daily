"""
AI 摘要模块。
使用阿里云通义千问 DashScope API，从候选新闻中筛选 Top 10 并生成中文摘要。
URL 不会传给 AI — 摘要完成后通过标题匹配回原始链接，避免 AI 篡改 URL。
降级策略：API 失败时返回纯标题列表。
"""

import json
import os
from difflib import SequenceMatcher
from typing import List, Dict, Optional

FALLBACK_CATEGORY = "综合"
MAX_NEWS = 10


def _title_similarity(a: str, b: str) -> float:
    """计算标题相似度"""
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def build_prompt(news_list: List[Dict]) -> str:
    """构建发给 AI 的 prompt（不含 URL）。"""
    news_text = ""
    for i, item in enumerate(news_list, 1):
        news_text += f"{i}. 【{item['source']}】{item['title']}\n"

    prompt = f"""你是一位资深财经编辑。以下是今日从多个财经网站抓取的热门新闻候选列表：

{news_text}

请完成以下任务：
1. 基于新闻的重要性和市场影响力，筛选出最重要的不超过{MAX_NEWS}条新闻
2. 按重要性从高到低排序
3. 为每条新闻撰写 2-3 句中文摘要，包含：核心事实 + 为什么重要 + 对市场的潜在影响
4. 为每条新闻标注一个最合适的分类：【宏观/股市/行业/公司/国际】

请严格按以下 JSON 数组格式返回，不要包含任何其他文字：
[
  {{
    "rank": 1,
    "title": "原标题",
    "source": "来源",
    "category": "宏观",
    "summary": "2-3句中文字摘要..."
  }}
]"""
    return prompt


def call_dashscope(prompt: str) -> Optional[str]:
    """
    调用 DashScope API，返回 AI 的原始文本响应。
    失败返回 None。
    """
    api_key = os.environ.get("DASHSCOPE_API_KEY", "")
    if not api_key:
        print("[summarizer] DASHSCOPE_API_KEY not set")
        return None

    import dashscope
    from dashscope import Generation

    try:
        response = Generation.call(
            model="qwen-plus",
            messages=[{"role": "user", "content": prompt}],
            result_format="message",
            api_key=api_key,
        )
        if response.status_code == 200:
            return response.output.choices[0].message.content
        else:
            print(f"[summarizer] API error: {response.code} - {response.message}")
            return None
    except Exception as e:
        print(f"[summarizer] API exception: {e}")
        return None


def parse_ai_response(raw_text: Optional[str]) -> List[Dict]:
    """
    解析 AI 返回的 JSON，补充缺失字段默认值。
    解析失败返回空列表。
    """
    if not raw_text:
        return []

    text = raw_text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

    try:
        items = json.loads(text)
        if not isinstance(items, list):
            return []
    except json.JSONDecodeError:
        return []

    result = []
    for i, item in enumerate(items):
        if not isinstance(item, dict) or not item.get("title"):
            continue
        result.append({
            "rank": item.get("rank", i + 1),
            "title": item["title"],
            "source": item.get("source", "未知"),
            "category": item.get("category", FALLBACK_CATEGORY),
            "summary": item.get("summary", "暂无摘要"),
        })

    return result


def _restore_urls(ai_results: List[Dict], original_news: List[Dict]) -> List[Dict]:
    """
    通过标题相似度将 AI 结果匹配回原始新闻，恢复正确的 URL。
    """
    for item in ai_results:
        best_match = None
        best_score = 0.0
        for orig in original_news:
            score = _title_similarity(item["title"], orig["title"])
            if score > best_score:
                best_score = score
                best_match = orig

        if best_match and best_score >= 0.50:
            item["url"] = best_match.get("url", "")
            # 如果 AI 返回的来源为"未知"，用原始来源补上
            if item["source"] == "未知":
                item["source"] = best_match.get("source", "未知")
        else:
            item["url"] = ""

    return ai_results


def fallback_summary(news_list: List[Dict]) -> List[Dict]:
    """
    降级方案：不调用 AI，直接返回去重后的标题+链接列表。
    """
    from scraper import deduplicate_news

    deduped = deduplicate_news(news_list)[:MAX_NEWS]
    return [
        {
            "rank": i + 1,
            "title": item["title"],
            "source": item.get("source", "未知"),
            "category": FALLBACK_CATEGORY,
            "summary": "（AI 摘要暂时不可用）",
            "url": item.get("url", ""),
        }
        for i, item in enumerate(deduped)
    ]


def summarize_news(news_list: List[Dict]) -> List[Dict]:
    """
    对新闻列表进行 AI 筛选和摘要生成。
    URL 不传给 AI，摘要完成后通过标题匹配回原始链接。
    失败时自动降级为纯标题列表。

    参数:
        news_list: 爬虫产出的新闻列表 [{title, url, source, hot_score}, ...]
    返回:
        摘要后的新闻列表 [{rank, title, source, category, summary, url}, ...]
    """
    if not news_list:
        return []

    from scraper import deduplicate_news

    deduped = deduplicate_news(news_list)
    prompt = build_prompt(deduped)
    raw = call_dashscope(prompt)

    ai_results = parse_ai_response(raw)
    if ai_results:
        # 关键：用原始 URL 替换 AI 可能胡编的 URL
        result = _restore_urls(ai_results, deduped)
        return result[:MAX_NEWS]

    # AI 失败，降级
    print("[summarizer] AI failed, falling back to title list")
    return fallback_summary(news_list)
