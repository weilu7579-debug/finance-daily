"""
财经新闻爬虫模块。
从新浪财经、同花顺、东方财富、网易财经、财联社、东方财富 7×24 快讯共 6 大数据源抓取当日热门新闻。
每个源并行请求，15 秒超时，单源失败不影响其他源。
"""

import json
import logging
import time
import traceback
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from difflib import SequenceMatcher
from typing import List, Dict

logger = logging.getLogger()
logger.setLevel(logging.INFO)

TIMEOUT = 15
MAX_PER_SOURCE = 8

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)
JSON_HEADERS = {
    "User-Agent": UA,
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


def _similarity(a: str, b: str) -> float:
    """计算两个字符串的相似度 (0.0 ~ 1.0)。"""
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _extract_bracket_title(text: str) -> str:
    """从财联社 brief/content 的【标题】前缀截取标题；无则取前 60 字兜底。"""
    if not text:
        return ""
    text = text.strip()
    if text.startswith("【"):
        end = text.find("】")
        if end > 0:
            inner = text[1:end].strip()
            if inner:
                return inner
    return text[:60]


# ── 新浪财经 ────────────────────────────────────────────

def fetch_sina_news() -> List[Dict]:
    """
    新浪财经滚动要闻。
    """
    try:
        url = (
            "https://feed.mix.sina.com.cn/api/roll/get?"
            "pageid=153&lid=2509&k=&num=10&page=1"
        )
        resp = requests.get(url, timeout=TIMEOUT, headers={
            **JSON_HEADERS,
            "Referer": "https://finance.sina.com.cn/",
        })
        resp.raise_for_status()
        data = resp.json()

        items = []
        raw_data = data.get("result", {}).get("data", [])
        logger.info(f"[sina] got {len(raw_data)} raw items")

        for item in raw_data[:MAX_PER_SOURCE]:
            title = item.get("title", "").strip()
            url = item.get("url", "")
            # 新浪可能返回相对路径
            if url and not url.startswith("http"):
                url = f"https:{url}" if url.startswith("//") else f"https://finance.sina.com.cn{url}"
            if title:
                items.append({
                    "title": title,
                    "url": url,
                    "source": "新浪财经",
                    "hot_score": int(item.get("ctime", 0)) // 1000,
                })
        logger.info(f"[sina] parsed {len(items)} items")
        return items
    except Exception:
        logger.error(f"[sina] FAILED: {traceback.format_exc()}")
        return []


# ── 同花顺 ──────────────────────────────────────────────

def fetch_10jqka_news() -> List[Dict]:
    """
    同花顺财经新闻（push/stock 接口）。
    """
    try:
        url = (
            "https://news.10jqka.com.cn/tapp/news/push/stock/?"
            "page=1&tag=&track=website&pagesize=10"
        )
        resp = requests.get(url, timeout=TIMEOUT, headers={
            **JSON_HEADERS,
            "Referer": "https://news.10jqka.com.cn/",
        })
        resp.raise_for_status()
        data = resp.json()

        if str(data.get("code")) != "200":
            logger.warning(f"[10jqka] bad response: code={data.get('code')}")
            return []

        items = []
        raw_list = data.get("data", {}).get("list", [])
        logger.info(f"[10jqka] got {len(raw_list)} raw items")

        for item in raw_list[:MAX_PER_SOURCE]:
            title = item.get("title", "").strip()
            url = item.get("url", "")
            if url and not url.startswith("http"):
                url = f"https://news.10jqka.com.cn{url}" if url.startswith("/") else f"https://news.10jqka.com.cn/{url}"
            if title:
                items.append({
                    "title": title,
                    "url": url,
                    "source": "同花顺",
                    "hot_score": int(item.get("ctime", 0)) or int(item.get("id", 0)),
                })
        logger.info(f"[10jqka] parsed {len(items)} items")
        return items
    except Exception:
        logger.error(f"[10jqka] FAILED: {traceback.format_exc()}")
        return []


# ── 东方财富 ────────────────────────────────────────────

def fetch_eastmoney_news() -> List[Dict]:
    """
    东方财富财经要闻（getNewsByColumns 接口，column=350）。
    """
    try:
        req_trace = int(time.time() * 1000)
        url = (
            "https://np-listapi.eastmoney.com/comm/web/getNewsByColumns?"
            "client=web&biz=web_news_col&column=350&order=1&needInteractData=0&"
            f"page_index=1&page_size=10&req_trace={req_trace}"
        )
        resp = requests.get(url, timeout=TIMEOUT, headers={
            **JSON_HEADERS,
            "Referer": "https://www.eastmoney.com/",
        })
        resp.raise_for_status()
        data = resp.json()

        if str(data.get("code")) != "1":
            logger.warning(f"[eastmoney] bad response: code={data.get('code')}, message={data.get('message')}")
            return []

        items = []
        raw_list = data.get("data", {}).get("list", [])
        logger.info(f"[eastmoney] got {len(raw_list)} raw items")

        for item in raw_list[:MAX_PER_SOURCE]:
            title = item.get("title", "").strip()
            url = item.get("url") or item.get("uniqueUrl") or ""
            if url:
                url = url.replace("http://", "https://", 1)
            elif item.get("code"):
                url = f"https://finance.eastmoney.com/a/{item['code']}.html"
            if title:
                items.append({
                    "title": title,
                    "url": url,
                    "source": "东方财富",
                    "hot_score": 0,
                })
        logger.info(f"[eastmoney] parsed {len(items)} items")
        return items
    except Exception:
        logger.error(f"[eastmoney] FAILED: {traceback.format_exc()}")
        return []


# ── 网易财经 ────────────────────────────────────────────

def fetch_netease_news() -> List[Dict]:
    """
    网易财经新闻流（JSONP 接口，需剥壳 data_callback(...)）。
    """
    try:
        url = "https://money.163.com/special/00259BVP/news_flow_index.js"
        resp = requests.get(url, timeout=TIMEOUT, headers={
            **JSON_HEADERS,
            "Referer": "https://money.163.com/",
        })
        resp.raise_for_status()

        text = resp.text.strip()
        prefix = "data_callback("
        if text.startswith(prefix):
            text = text[len(prefix):]
        if text.endswith(")"):
            text = text[:-1]
        data = json.loads(text)

        items = []
        logger.info(f"[netease] got {len(data)} raw items")

        for item in data[:MAX_PER_SOURCE]:
            title = item.get("title", "").strip()
            url = item.get("docurl") or item.get("tlink") or ""
            if url.startswith("http://"):
                url = "https://" + url[len("http://"):]
            if title:
                items.append({
                    "title": title,
                    "url": url,
                    "source": "网易财经",
                    "hot_score": int(item.get("tienum", 0)),
                })
        logger.info(f"[netease] parsed {len(items)} items")
        return items
    except Exception:
        logger.error(f"[netease] FAILED: {traceback.format_exc()}")
        return []


# ── 财联社 ──────────────────────────────────────────────

def fetch_cls_news() -> List[Dict]:
    """
    财联社电报（api/cache 公开接口，免签名）。
    过滤 type==20015（盘中宝付费项）与 id<=0（占位/分隔项），title 空时从 brief/content 兜底。
    """
    try:
        url = "https://www.cls.cn/api/cache?app=CailianpressWeb&name=telegraph&os=web&sv=8.7.9"
        resp = requests.get(url, timeout=TIMEOUT, headers={
            **JSON_HEADERS,
            "Referer": "https://www.cls.cn/telegraph",
        })
        resp.raise_for_status()
        data = resp.json()

        if data.get("errno") != 0:
            logger.warning(f"[cls] bad response: errno={data.get('errno')}")
            return []

        items = []
        raw_list = data.get("data", {}).get("roll_data", [])
        logger.info(f"[cls] got {len(raw_list)} raw items")

        for item in raw_list[:MAX_PER_SOURCE]:
            item_id = item.get("id", 0)
            item_type = item.get("type", -1)
            if item_id <= 0 or item_type == 20015:
                continue
            title = item.get("title", "").strip()
            if not title:
                raw = item.get("brief") or item.get("content") or ""
                title = _extract_bracket_title(raw)
            if not title:
                continue
            items.append({
                "title": title,
                "url": f"https://www.cls.cn/detail/{item_id}",
                "source": "财联社",
                "hot_score": int(item.get("reading_num", 0)) or int(item.get("ctime", 0)),
            })
        logger.info(f"[cls] parsed {len(items)} items")
        return items
    except Exception:
        logger.error(f"[cls] FAILED: {traceback.format_exc()}")
        return []


# ── 东方财富 7×24 快讯 ──────────────────────────────────

def fetch_eastmoney_724_news() -> List[Dict]:
    """
    东方财富 7×24 小时快讯（getFastNewsList 接口）。
    """
    try:
        req_trace = int(time.time() * 1000)
        url = (
            "https://np-listapi.eastmoney.com/comm/web/getFastNewsList?"
            "client=web&biz=web_724&fastColumn=102&sortEnd=&pageSize=10&"
            f"req_trace={req_trace}"
        )
        resp = requests.get(url, timeout=TIMEOUT, headers={
            **JSON_HEADERS,
            "Referer": "https://www.eastmoney.com/",
        })
        resp.raise_for_status()
        data = resp.json()

        if str(data.get("code")) != "1":
            logger.warning(f"[eastmoney724] bad response: code={data.get('code')}, message={data.get('message')}")
            return []

        items = []
        raw_list = data.get("data", {}).get("fastNewsList", [])
        logger.info(f"[eastmoney724] got {len(raw_list)} raw items")

        for item in raw_list[:MAX_PER_SOURCE]:
            title = item.get("title", "").strip()
            code = item.get("code", "")
            url = f"https://finance.eastmoney.com/a/{code}.html" if code else ""
            if title:
                items.append({
                    "title": title,
                    "url": url,
                    "source": "东方财富 7×24 快讯",
                    "hot_score": int(item.get("pinglun_Num", 0)) or int(item.get("realSort", 0)),
                })
        logger.info(f"[eastmoney724] parsed {len(items)} items")
        return items
    except Exception:
        logger.error(f"[eastmoney724] FAILED: {traceback.format_exc()}")
        return []


# ── 源注册表 ────────────────────────────────────────────

SOURCE_REGISTRY: List[Dict] = [
    {"name": "新浪财经", "fetch": fetch_sina_news},
    {"name": "同花顺", "fetch": fetch_10jqka_news},
    {"name": "东方财富", "fetch": fetch_eastmoney_news},
    {"name": "网易财经", "fetch": fetch_netease_news},
    {"name": "财联社", "fetch": fetch_cls_news},
    {"name": "东方财富 7×24 快讯", "fetch": fetch_eastmoney_724_news},
]


# ── 编排 ────────────────────────────────────────────────

def scrape_all() -> List[Dict]:
    """
    并行抓取全部数据源，返回汇总新闻列表。
    单个源失败不影响其他源。
    """
    all_news = []
    with ThreadPoolExecutor(max_workers=len(SOURCE_REGISTRY)) as executor:
        futures = {executor.submit(src["fetch"]): src["name"] for src in SOURCE_REGISTRY}
        for future in as_completed(futures):
            name = futures[future]
            try:
                result = future.result()
                logger.info(f"[scrape_all] {name} returned {len(result)} items")
                all_news.extend(result)
            except Exception:
                logger.error(f"[scrape_all] {name} exception: {traceback.format_exc()}")

    logger.info(f"[scrape_all] total raw: {len(all_news)}")
    return all_news


def deduplicate_news(news_list: List[Dict], threshold: float = 0.80) -> List[Dict]:
    """
    基于标题文本相似度去重。
    threshold: 相似度阈值，超过此值视为重复（保留 hot_score 高的）。
    """
    if not news_list:
        return []

    sorted_news = sorted(news_list, key=lambda x: x.get("hot_score", 0), reverse=True)
    kept = []

    for item in sorted_news:
        is_dup = False
        for k in kept:
            if _similarity(item["title"], k["title"]) >= threshold:
                is_dup = True
                break
        if not is_dup:
            kept.append(item)

    logger.info(f"[deduplicate] {len(news_list)} -> {len(kept)}")
    return kept
