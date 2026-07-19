"""
每日财经新闻邮件速览 — 主入口。
编排爬虫 → AI 摘要 → 邮件发送的完整流程。
同时提供阿里云函数计算的 handler 入口。
"""

import json
import logging
import traceback
from datetime import datetime

from scraper import scrape_all
from summarizer import summarize_news
from mailer import send_email, send_alert_email

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def run_daily_report() -> dict:
    """
    执行一次完整的日报流程。
    返回 {"status": "ok"|"partial"|"failed", "news_count": int, "error": str|None}
    """
    errors = []

    # 1. 爬取新闻
    logger.info("[main] Starting news scraping...")
    raw_news = scrape_all()
    logger.info(f"[main] Scraped {len(raw_news)} raw news items")

    if not raw_news:
        error_msg = "所有数据源均抓取失败"
        logger.error(f"[main] {error_msg}")
        send_alert_email(error_msg)
        return {"status": "failed", "news_count": 0, "error": error_msg}

    # 2. AI 摘要
    logger.info("[main] Starting AI summarization...")
    summarized = summarize_news(raw_news)
    logger.info(f"[main] Summarized to {len(summarized)} items")

    if not summarized:
        errors.append("AI 摘要返回空结果")

    # 3. 发送邮件
    logger.info("[main] Sending email...")
    sent = send_email(summarized)

    if sent:
        logger.info("[main] Daily report sent successfully")
        status = "partial" if errors else "ok"
        return {"status": status, "news_count": len(summarized), "error": "; ".join(errors) if errors else None}
    else:
        logger.error("[main] Email sending failed")
        return {"status": "failed", "news_count": len(summarized), "error": "邮件发送失败"}


def handler(event, context):
    """
    阿里云函数计算 FC 的 handler 入口。
    由定时触发器调用，也支持手动调用。
    """
    logger.info(f"[main] Handler invoked at {datetime.now().isoformat()}")
    logger.info(f"[main] Event: {json.dumps(event, ensure_ascii=False, default=str)}")

    try:
        result = run_daily_report()
        logger.info(f"[main] Result: {json.dumps(result, ensure_ascii=False)}")
        return {
            "statusCode": 200 if result["status"] != "failed" else 500,
            "body": json.dumps(result, ensure_ascii=False),
        }
    except Exception as e:
        tb = traceback.format_exc()
        logger.error(f"[main] Unexpected error: {tb}")
        send_alert_email(tb)
        return {
            "statusCode": 500,
            "body": json.dumps({"status": "failed", "error": str(e)}, ensure_ascii=False),
        }


# 支持本地直接运行
if __name__ == "__main__":
    result = run_daily_report()
    print(json.dumps(result, ensure_ascii=False, indent=2))
