"""
邮件发送模块。
使用 Jinja2 渲染 HTML 模板，通过 SMTP SSL 发送邮件。
支持重试 3 次（间隔 30s）。
"""

import os
import smtplib
import time
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List, Dict
from jinja2 import Environment, FileSystemLoader, select_autoescape

# Jinja2 环境，模板在相同目录
_TEMPLATE_DIR = os.path.dirname(os.path.abspath(__file__))
_env = Environment(
    loader=FileSystemLoader(_TEMPLATE_DIR),
    autoescape=select_autoescape(["html", "xml"]),
)

EMAIL_SUBJECT = "📰 每日财经速览"
WEEKDAY_NAMES = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


def _get_date_str() -> str:
    """生成日期字符串，如 '2026年6月8日 · 周一'"""
    now = datetime.now()
    return f"{now.year}年{now.month}月{now.day}日 · {WEEKDAY_NAMES[now.weekday()]}"


def render_email_html(news_list: List[Dict]) -> str:
    """
    渲染邮件 HTML 内容。
    参数:
        news_list: 摘要后的新闻列表 [{rank, title, source, category, summary, url}, ...]
    返回:
        完整的 HTML 字符串
    """
    template = _env.get_template("template.html")
    return template.render(
        news=news_list,
        date_str=_get_date_str(),
    )


def send_email(news_list: List[Dict], max_retries: int = 3) -> bool:
    """
    发送邮件。
    参数:
        news_list: 摘要后的新闻列表
        max_retries: 最大重试次数
    返回:
        True 如果发送成功，False 如果全部失败
    """
    smtp_host = os.environ.get("SMTP_HOST", "smtp.qq.com")
    smtp_port = int(os.environ.get("SMTP_PORT", "465"))
    smtp_user = os.environ.get("SMTP_USER", "")
    smtp_pass = os.environ.get("SMTP_PASS", "")
    to_email = os.environ.get("TO_EMAIL", smtp_user)

    if not smtp_user or not smtp_pass:
        print("[mailer] SMTP credentials not configured")
        return False

    html_content = render_email_html(news_list)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = EMAIL_SUBJECT
    msg["From"] = smtp_user
    msg["To"] = to_email
    msg.attach(MIMEText(html_content, "html", "utf-8"))

    for attempt in range(1, max_retries + 1):
        try:
            with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=30) as server:
                server.login(smtp_user, smtp_pass)
                server.sendmail(smtp_user, to_email, msg.as_string())
            print(f"[mailer] Email sent successfully (attempt {attempt})")
            return True
        except Exception as e:
            print(f"[mailer] Send failed (attempt {attempt}/{max_retries}): {e}")
            if attempt < max_retries:
                time.sleep(30)

    print("[mailer] All send attempts failed")
    return False


def send_alert_email(error_log: str) -> bool:
    """
    发送告警邮件（如全部数据源失败时）。
    参数:
        error_log: 错误日志内容
    """
    smtp_host = os.environ.get("SMTP_HOST", "smtp.qq.com")
    smtp_port = int(os.environ.get("SMTP_PORT", "465"))
    smtp_user = os.environ.get("SMTP_USER", "")
    smtp_pass = os.environ.get("SMTP_PASS", "")
    to_email = os.environ.get("TO_EMAIL", smtp_user)

    if not smtp_user or not smtp_pass:
        return False

    msg = MIMEText(
        f"每日财经新闻日报生成失败\n\n"
        f"时间：{_get_date_str()}\n\n"
        f"错误日志：\n{error_log}\n\n"
        f"请检查爬虫数据源或网络连接。",
        "plain", "utf-8",
    )
    msg["Subject"] = "⚠️ 财经日报生成失败"
    msg["From"] = smtp_user
    msg["To"] = to_email

    try:
        with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=30) as server:
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_user, to_email, msg.as_string())
        return True
    except Exception as e:
        print(f"[mailer] Alert email failed: {e}")
        return False
