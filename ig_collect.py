"""내 PC(하루 1~2회): 인스타 키워드 검색 → 게시물 본문 → LLM 판정 → 텔레그램
결과는 data/ig_events.json 에 저장되고 run_ig.bat 이 GitHub에 올립니다."""
import random
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from playwright.sync_api import sync_playwright

from bot import buttons_for, format_event, send
from common import (DATA, MAX_AGE_DAYS, ROOT, build_event, decide, event_id,
                    feedback_examples, load_json, prefilter, prune_events, prune_seen,
                    rule_classify, save_json)
from llm import analyze

IG_KEYWORDS = [
    "벼룩시장 판매자 모집", "플리마켓 셀러 모집", "나눔장터 판매자 모집",
    "프리마켓 셀러모집", "벼룩시장 참가자 모집", "중고 플리마켓 모집",
]
POSTS_PER_KEYWORD = 15
STATE_PATH = ROOT / "ig_state.json"            # 로그인 세션 (절대 업로드 금지)
LOCAL_PATH = DATA / "ig_local_state.json"      # LLM 사용량 (PC 전용)
CODE_RE = re.compile(r"/(?:p|reel)/([A-Za-z0-9_-]+)")


def pause(a=3, b=6):
    time.sleep(random.uniform(a, b))


def logged_out(page):
    return "accounts/login" in page.url or "challenge" in page.url


def read_post(page, url):
    page.goto(url, wait_until="domcontentloaded")
    pause(3, 5)
    og_desc = page.get_attribute('meta[property="og:description"]', "content") or ""
    og_title = page.get_attribute('meta[property="og:title"]', "content") or ""
    caption = page.locator("h1").first.inner_text() if page.locator("h1").count() else ""
    dt = None
    t = page.locator("time[datetime]")
    if t.count():
        try:
            dt = datetime.fromisoformat(t.first.get_attribute("datetime").replace("Z", "+00:00"))
        except (TypeError, ValueError):
            pass
    return og_title, (caption if len(caption) > len(og_desc) else og_desc), dt


def collect(page, seen):
    cutoff = datetime.now(timezone.utc) - timedelta(days=MAX_AGE_DAYS)
    cands = []
    for kw in IG_KEYWORDS:
        page.goto("https://www.instagram.com/explore/search/keyword/?q=" + quote(kw),
                  wait_until="domcontentloaded")
        pause(5, 8)
        if logged_out(page):
            send("🔒 인스타 로그인이 풀렸어요. PC에서 python ig_login.py 를 다시 실행해 주세요.")
            return cands
        for _ in range(2):
            page.mouse.wheel(0, 3000)
            pause(2, 4)
        codes = []
        for h in page.eval_on_selector_all("a[href]", "els => els.map(e => e.href)"):
            m = CODE_RE.search(h)
            if m and m.group(1) not in codes:
                codes.append(m.group(1))
        for code in codes[:POSTS_PER_KEYWORD]:
            url = f"https://www.instagram.com/p/{code}"
            if url in seen:
                continue
            try:
                title, text, dt = read_post(page, url)
            except Exception as ex:
                print("게시물 읽기 실패:", url, ex)
                continue
            if logged_out(page):
                return cands
            seen[url] = time.time()
            if (dt and dt < cutoff) or not prefilter(text):
                continue
            cands.append({"key": url, "url": url, "source": "인스타그램",
                          "title": (title or "인스타그램 게시물")[:150], "text": text,
                          "date": dt.strftime("%Y-%m-%d") if dt else ""})
        pause(8, 15)
    return cands


def main():
    if not STATE_PATH.exists():
        sys.exit("먼저 python ig_login.py 로 로그인하세요.")
    seen = load_json(DATA / "ig_seen.json", {})
    ig_events = load_json(DATA / "ig_events.json", {})
    events = load_json(DATA / "events.json", {})
    status = load_json(DATA / "status.json", {})
    local = load_json(LOCAL_PATH, {})

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(storage_state=str(STATE_PATH), locale="ko-KR",
                                  viewport={"width": 1280, "height": 900})
        cands = collect(ctx.new_page(), seen)
        browser.close()

    all_events = {**events, **ig_events}
    fb_text, has_dislikes = feedback_examples(all_events, status, load_json(DATA / "state.json", {}).get("prefs", []))
    analyses = analyze(cands, local.setdefault("llm_usage", {}), fb_text)
    known = {ev["ekey"] for ev in all_events.values() if ev.get("ekey")}

    sent = 0
    for it in cands:
        a = analyses.get(it["key"])
        label = decide(a, has_dislikes) if a else rule_classify(it["text"])
        if not label:
            continue
        ev = build_event(it, a, label)
        if ev["ekey"] and ev["ekey"] in known:
            continue
        if ev["ekey"]:
            known.add(ev["ekey"])
        eid = event_id(it["key"])
        ev["notified"] = send(format_event(ev), buttons_for(eid))
        ig_events[eid] = ev
        sent += ev["notified"]

    save_json(DATA / "ig_seen.json", prune_seen(seen))
    save_json(DATA / "ig_events.json", prune_events(ig_events))
    save_json(LOCAL_PATH, local)
    print(f"{datetime.now():%Y-%m-%d %H:%M} 인스타 후보 {len(cands)} · 전송 {sent}")


if __name__ == "__main__":
    main()
