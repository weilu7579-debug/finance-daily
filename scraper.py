"""
财经新闻爬虫模块。
从东方财富、新浪财经、雪球、华尔街见闻抓取当日热门新闻。
每个源并行请求，10 秒超时，单源失败不影响其他源。
"""

import logging
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


# ── 东方财富 ────────────────────────────────────────────

def fetch_eastmoney_news() -> List[Dict]:
    """
    东方财富 24 小时热门要闻。
    使用 push2 API — 更稳定的接口。
    """
    try:
        # 使用东方财富行情中心的新闻接口
        url = (
            "https://push2.eastmoney.com/api/qt/ulist.np/get?"
            "fltt=2&invt=2&fields=f3,f12,f14&secids=1.000001,0.399001&"
            "np=1&ut=bd1d9ddb04089700cf9c27f6f7426281&cb=json"
        )
        # 改用新闻列表接口
        news_url = (
            "https://np-listapi.eastmoney.com/comm/api/getNewsList?"
            "client=web&biz=news&needHasVideo=0&needScore=1&"
            "pageIndex=1&pageSize=10&sort=hot"
        )
        resp = requests.get(news_url, timeout=TIMEOUT, headers={
            **JSON_HEADERS,
            "Referer": "https://www.eastmoney.com/",
        })
        resp.raise_for_status()
        data = resp.json()
        if resp.status_code != 200 or not data.get("data"):
            logger.warning(f"[eastmoney] bad response: status={resp.status_code}, keys={list(data.keys()) if data else 'empty'}")
            return []

        items = []
        raw_list = data.get("data", {}).get("list", [])
        logger.info(f"[eastmoney] got {len(raw_list)} raw items")

        for item in raw_list[:MAX_PER_SOURCE]:
            title = item.get("title", "").strip()
            url = item.get("url", "")
            # 如果 url 为空或相对路径，构造完整 URL
            if url and not url.startswith("http"):
                url = f"https://www.eastmoney.com{url}" if url.startswith("/") else f"https://www.eastmoney.com/{url}"
            if title:
                items.append({
                    "title": title,
                    "url": url,
                    "source": "东方财富",
                    "hot_score": int(item.get("score", 0)),
                })
        logger.info(f"[eastmoney] parsed {len(items)} items")
        return items
    except Exception:
        logger.error(f"[eastmoney] FAILED: {traceback.format_exc()}")
        return []


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


# ── 雪球 ────────────────────────────────────────────────

def fetch_xueqiu_news() -> List[Dict]:
    """
    雪球今日热议话题。
    """
    try:
        session = requests.Session()
        session.headers.update(JSON_HEADERS)

        # 先访问首页获取 cookie
        home = session.get("https://xueqiu.com/", timeout=TIMEOUT)
        home.raise_for_status()

        # 请求热议接口
        resp = session.get(
            "https://xueqiu.com/statuses/hot/listV2.json",
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()

        raw_items = data.get("items", [])
        logger.info(f"[xueqiu] got {len(raw_items)} raw items")

        items = []
        for item in raw_items[:MAX_PER_SOURCE]:
            title = item.get("title", "") or item.get("text", "")
            target = item.get("target", "")
            url = target
            if target and not target.startswith("http"):
                url = f"https://xueqiu.com{target}"
            if title:
                items.append({
                    "title": title.strip(),
                    "url": url,
                    "source": "雪球",
                    "hot_score": int(item.get("reply_count", 0)) or int(item.get("like_count", 0)),
                })
        logger.info(f"[xueqiu] parsed {len(items)} items")
        return items
    except Exception:
        logger.error(f"[xueqiu] FAILED: {traceback.format_exc()}")
        return []


# ── 华尔街见闻 ──────────────────────────────────────────

def fetch_wallstreetcn_news() -> List[Dict]:
    """
    华尔街见闻快讯 / 热门文章。
    """
    try:
        # 使用 lives API 获取快讯
        url = "https://api-one.wallstcn.com/apiv1/content/lives?limit=15&channel=global"
        resp = requests.get(url, timeout=TIMEOUT, headers=JSON_HEADERS)
        resp.raise_for_status()
        data = resp.json()

        raw_items = data.get("data", {}).get("items", [])
        logger.info(f"[wallstreetcn] got {len(raw_items)} raw items")

        items = []
        for item in raw_items[:MAX_PER_SOURCE]:
            title = item.get("title", "").strip()
            if not title:
                content = item.get("content_text", "").strip()
                title = content[:80] if content else ""
            item_id = item.get("id", "")
            url = f"https://wallstreetcn.com/livenews/{item_id}" if item_id else ""

            if title:
                items.append({
                    "title": title,
                    "url": url,
                    "source": "华尔街见闻",
                    "hot_score": 50,
                })
        logger.info(f"[wallstreetcn] parsed {len(items)} items")
        return items
    except Exception:
        logger.error(f"[wallstreetcn] FAILED: {traceback.format_exc()}")
        return []


# ── 备用源：澎湃财经 ────────────────────────────────────

def fetch_thepaper_news() -> List[Dict]:
    """
    备用源：澎湃财经。
    仅在主要源全部失败时提供后备。
    """
    try:
        url = "https://cache.thepaper.cn/contentapi/wwwIndex/rightSidebar"
        resp = requests.get(url, timeout=TIMEOUT, headers={
            **JSON_HEADERS,
            "Referer": "https://www.thepaper.cn/",
        })
        resp.raise_for_status()
        data = resp.json()

        # 尝试从财经频道获取
        finance_url = "https://api.thepaper.cn/contentapi/nodeCont/25949?pageidx=0&pagesize=10"
        resp2 = requests.get(finance_url, timeout=TIMEOUT, headers=JSON_HEADERS)
        resp2.raise_for_status()
        data2 = resp2.json()

        items = []
        for item in data2.get("data", {}).get("list", [])[:MAX_PER_SOURCE]:
            title = item.get("name", "").strip()
            url = item.get("link", "") or f"https://www.thepaper.cn/newsDetail_forward_{item.get('contId', '')}"
            if title:
                items.append({
                    "title": title,
                    "url": url,
                    "source": "澎湃财经",
                    "hot_score": int(item.get("praiseTimes", 0)),
                })
        logger.info(f"[thepaper] parsed {len(items)} items")
        return items
    except Exception:
        logger.error(f"[thepaper] FAILED: {traceback.format_exc()}")
        return []


# ── 编排 ────────────────────────────────────────────────

def scrape_all() -> List[Dict]:
    """
    并行抓取全部数据源，返回汇总新闻列表。
    单个源失败不影响其他源。
    """
    sources = [
        fetch_eastmoney_news,
        fetch_sina_news,
        fetch_xueqiu_news,
        fetch_wallstreetcn_news,
    ]

    all_news = []
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(fn): getattr(fn, '__name__', str(fn)) for fn in sources}
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
