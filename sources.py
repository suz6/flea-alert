"""네이버 · 카카오(다음) · 구글 알리미 수집 + 원문 본문 가져오기"""
import os
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import parse_qs, urlparse

import feedparser
import requests
from bs4 import BeautifulSoup

from common import MARKET_WORDS, clean

UA = {"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
                    "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"}


def _item(source, title, snippet, url, dt=None):
    return {"source": source, "title": clean(title), "snippet": clean(snippet), "url": url,
            "dt": dt, "date": dt.strftime("%Y-%m-%d") if dt else ""}


def naver(keyword):
    cid, secret = os.environ.get("NAVER_CLIENT_ID"), os.environ.get("NAVER_CLIENT_SECRET")
    if not cid or not secret:
        return []
    headers = {"X-Naver-Client-Id": cid, "X-Naver-Client-Secret": secret}
    out = []
    for kind, label in [("blog", "네이버 블로그"), ("cafearticle", "네이버 카페"), ("news", "네이버 뉴스")]:
        try:
            r = requests.get(f"https://openapi.naver.com/v1/search/{kind}.json",
                             params={"query": keyword, "display": 30, "sort": "date"},
                             headers=headers, timeout=15)
            r.raise_for_status()
        except requests.RequestException as ex:
            print("네이버 오류:", kind, ex)
            continue
        for it in r.json().get("items", []):
            dt = None
            try:
                if it.get("postdate"):
                    dt = datetime.strptime(it["postdate"], "%Y%m%d").replace(tzinfo=timezone.utc)
                elif it.get("pubDate"):
                    dt = parsedate_to_datetime(it["pubDate"])
            except (ValueError, TypeError):
                pass
            url = it.get("originallink") or it.get("link")
            out.append(_item(label, it.get("title"), it.get("description"), url, dt))
    return out


def kakao(keyword):
    key = os.environ.get("KAKAO_REST_KEY")
    if not key:
        return []
    out = []
    for kind, label in [("web", "다음 웹"), ("blog", "다음 블로그"), ("cafe", "다음 카페")]:
        try:
            r = requests.get(f"https://dapi.kakao.com/v2/search/{kind}",
                             params={"query": keyword, "sort": "recency", "size": 30},
                             headers={"Authorization": f"KakaoAK {key}"}, timeout=15)
            r.raise_for_status()
        except requests.RequestException as ex:
            print("카카오 오류:", kind, ex)
            continue
        for it in r.json().get("documents", []):
            dt = None
            try:
                dt = datetime.fromisoformat(it["datetime"]) if it.get("datetime") else None
            except ValueError:
                pass
            out.append(_item(label, it.get("title"), it.get("contents"), it.get("url"), dt))
    return out


def google_alerts():
    feeds = [u.strip() for u in os.environ.get("GOOGLE_ALERT_FEEDS", "").split(",") if u.strip()]
    out = []
    for feed_url in feeds:
        for e in feedparser.parse(feed_url).entries:
            link = e.get("link", "")
            q = parse_qs(urlparse(link).query)
            if "url" in q:
                link = q["url"][0]
            dt = datetime(*e.published_parsed[:6], tzinfo=timezone.utc) if e.get("published_parsed") else None
            out.append(_item("구글 알리미", e.get("title"), e.get("summary"), link, dt))
    return out


def full_text(item, limit=2500):
    """원문 페이지에서 본문 가져오기 (카페는 로그인 필요해서 요약문 사용)"""
    if "카페" in item["source"]:
        return item["snippet"]
    url = item["url"]
    m = re.match(r"https?://blog\.naver\.com/([^/?#]+)/(\d+)", url)
    if m:
        url = f"https://m.blog.naver.com/{m.group(1)}/{m.group(2)}"
    try:
        r = requests.get(url, headers=UA, timeout=10)
        r.raise_for_status()
        if r.encoding in (None, "ISO-8859-1"):
            r.encoding = r.apparent_encoding
        soup = BeautifulSoup(r.text, "html.parser")
        for t in soup(["script", "style", "nav", "header", "footer", "aside", "form"]):
            t.decompose()
        node = soup.select_one(".se-main-container, #postViewArea, #dic_area, "
                               "#articleBodyContents, article") or soup.body or soup
        text = re.sub(r"\s+", " ", node.get_text(" ")).strip()
        hits = [text.find(w) for w in MARKET_WORDS if w in text]
        start = max(0, min(hits) - 300) if hits else 0
        text = text[start:start + limit]
        return text if len(text) > len(item["snippet"]) else item["snippet"]
    except Exception:
        return item["snippet"]
