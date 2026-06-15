"""
小鹏游艇新闻追踪器
- 每天自动搜索小鹏/飞鱼项目最新新闻
- 通过邮件推送（Gmail SMTP）
"""

import anthropic
import smtplib
import json
import os
import re
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# ─────────────────────────────────────────────
# 配置（全部从环境变量读取，由 GitHub Secrets 注入）
# ─────────────────────────────────────────────
CONFIG = {
    "anthropic_api_key": os.getenv("ANTHROPIC_API_KEY"),
    "email": {
        "enabled": True,
        "smtp_server": "smtp.gmail.com",
        "smtp_port": 587,
        "sender": os.getenv("EMAIL_SENDER") or "deyaz@uci.edu",
        "password": os.getenv("EMAIL_PASSWORD"),
        "recipients": [os.getenv("EMAIL_RECIPIENT") or "zhaodeya@gmail.com"],
    },
    "keywords": [
        "小鹏 游艇",
        "小鹏 飞鱼项目",
        "小鹏集团 新业务",
        "XPENG yacht 2026",
    ],
    "dedup_file": os.path.join(os.path.dirname(__file__), "sent_news.json"),
}

# ─────────────────────────────────────────────
# 核心：调用 Claude API 搜索新闻
# ─────────────────────────────────────────────
def fetch_news(keywords):
    client = anthropic.Anthropic(api_key=CONFIG["anthropic_api_key"])
    today = datetime.now().strftime("%Y年%m月%d日")
    kw_str = "、".join(keywords)

    prompt = f"""今天是{today}。请用 web_search 工具搜索以下关键词的最新新闻：
关键词：{kw_str}

搜索完成后，请严格返回如下 JSON 格式，不要有任何额外文字或 markdown：
{{
  "articles": [
    {{
      "title": "文章标题",
      "source": "媒体名称",
      "date": "发布日期 YYYY-MM-DD",
      "summary": "150字以内的核心内容摘要",
      "url": "原文链接",
      "tag": "分类：项目进展/融资/竞品/人事/其他"
    }}
  ]
}}

要求：
1. 只返回7天内的新闻
2. 优先选与小鹏游艇/飞鱼项目直接相关的
3. 最多返回8条
4. 只返回 JSON，不要任何解释、不要 markdown 代码块
5. 字符串内部不要出现英文双引号 " ，需要引用时一律用中文「」
6. 每个字段写成一行，summary 内不要换行"""

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=8000,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        messages=[{"role": "user", "content": prompt}],
    )

    text = ""
    for block in response.content:
        if block.type == "text":
            text += block.text

    data = _parse_articles(text)
    if data is None:
        print("[警告] JSON 解析失败，尝试让 Claude 修复...")
        data = _repair_articles(client, text)
    if data is None:
        print(f"[警告] 修复后仍无法解析，原始内容：\n{text}")
        return []
    return data


def _parse_articles(text):
    text = text.strip().replace("```json", "").replace("```", "").strip()
    try:
        return json.loads(text).get("articles", [])
    except json.JSONDecodeError:
        match = re.search(r'\{[\s\S]*\}', text)
        if match:
            try:
                return json.loads(match.group()).get("articles", [])
            except json.JSONDecodeError:
                return None
    return None


def _repair_articles(client, broken):
    prompt = (
        "下面的内容本应是 JSON，但格式有误。请修复成严格合法的 JSON，"
        "保持原有数据不变，只返回 JSON 本身，不要任何解释或 markdown：\n\n" + broken
    )
    resp = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=8000,
        messages=[{"role": "user", "content": prompt}],
    )
    fixed = "".join(b.text for b in resp.content if b.type == "text")
    return _parse_articles(fixed)


# ─────────────────────────────────────────────
# 去重
# ─────────────────────────────────────────────
def load_sent(path):
    if not os.path.exists(path):
        return set()
    with open(path, "r", encoding="utf-8") as f:
        return set(json.load(f))

def save_sent(path, titles):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(list(titles), f, ensure_ascii=False, indent=2)


# ─────────────────────────────────────────────
# 邮件 HTML
# ─────────────────────────────────────────────
def build_email_html(articles):
    today = datetime.now().strftime("%Y年%m月%d日")
    tag_colors = {
        "项目进展": "#185FA5", "融资": "#3B6D11", "竞品": "#993C1D",
        "人事": "#534AB7", "其他": "#5F5E5A",
    }
    rows = ""
    for a in articles:
        color = tag_colors.get(a.get("tag", "其他"), "#5F5E5A")
        url = a.get("url", "")
        link = f'<a href="{url}" style="color:#185FA5;text-decoration:none">{a["title"]}</a>' if url else a["title"]
        rows += f"""
        <tr><td style="padding:16px 0;border-bottom:1px solid #eee">
          <div style="margin-bottom:6px">
            <span style="font-size:11px;padding:2px 8px;border-radius:4px;background:{color}22;color:{color};font-weight:500">{a.get('tag','其他')}</span>
            <span style="font-size:12px;color:#888;margin-left:8px">{a.get('source','')} · {a.get('date','')}</span>
          </div>
          <div style="font-size:15px;font-weight:500;margin-bottom:6px">{link}</div>
          <div style="font-size:13px;color:#555;line-height:1.6">{a.get('summary','')}</div>
        </td></tr>"""
    return f"""<div style="font-family:-apple-system,sans-serif;max-width:600px;margin:0 auto;padding:24px">
      <h2 style="font-size:18px;font-weight:500;margin:0 0 4px">小鹏游艇 · 每日新闻追踪</h2>
      <p style="font-size:13px;color:#888;margin:0 0 24px">{today} · 共 {len(articles)} 条新消息</p>
      <table style="width:100%;border-collapse:collapse">{rows}</table>
      <p style="font-size:12px;color:#aaa;margin-top:24px;text-align:center">由 Claude API 自动生成</p>
    </div>"""


# ─────────────────────────────────────────────
# 推送
# ─────────────────────────────────────────────
def send_email(articles):
    cfg = CONFIG["email"]
    if not cfg["enabled"] or not cfg["sender"]:
        print("[!] 邮件未配置，跳过")
        return
    today = datetime.now().strftime("%Y-%m-%d")
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"【小鹏游艇追踪】{today} · {len(articles)}条新消息"
    msg["From"] = cfg["sender"]
    msg["To"] = ", ".join(cfg["recipients"])
    msg.attach(MIMEText(build_email_html(articles), "html", "utf-8"))
    try:
        with smtplib.SMTP(cfg["smtp_server"], cfg["smtp_port"]) as server:
            server.starttls()
            server.login(cfg["sender"], cfg["password"])
            server.sendmail(cfg["sender"], cfg["recipients"], msg.as_string())
        print(f"[✓] 邮件已发送至 {cfg['recipients']}")
    except Exception as e:
        print(f"[✗] 邮件发送失败：{e}")


# ─────────────────────────────────────────────
# 主流程
# ─────────────────────────────────────────────
def main():
    print(f"\n{'='*40}")
    print(f"小鹏游艇新闻追踪器  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*40}")

    print("[1/4] 搜索最新新闻...")
    articles = fetch_news(CONFIG["keywords"])
    print(f"      搜索到 {len(articles)} 条")
    if not articles:
        print("      没有新内容，退出。")
        return

    print("[2/4] 去重过滤...")
    sent = load_sent(CONFIG["dedup_file"])
    new_articles = [a for a in articles if a.get("title", "") not in sent]
    print(f"      过滤后剩余 {len(new_articles)} 条")
    if not new_articles:
        print("      全部已推送过，今日无新内容。")
        return

    print("[3/4] 推送中...")
    send_email(new_articles)

    print("[4/4] 记录已发送...")
    sent.update(a["title"] for a in new_articles)
    save_sent(CONFIG["dedup_file"], sent)
    print(f"\n完成！共推送 {len(new_articles)} 条新闻。")


if __name__ == "__main__":
    main()
