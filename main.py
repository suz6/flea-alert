"""GitHub Actions(1시간마다): 수집 → 1차 거르기 → 본문 읽기 → LLM 판정 → 텔레그램"""
import time
from datetime import datetime, timedelta, timezone

from bot import buttons_for, format_event, process_feedback, send
from common import (DATA, MAX_AGE_DAYS, MAX_ANALYZE_PER_RUN, MAX_NOTIFY_PER_RUN,
                    SEARCH_KEYWORDS, build_event, decide, event_id, feedback_examples,
                    load_json, norm_url, prefilter, prune_events, prune_seen,
                    rule_classify, save_json)
from llm import analyze
from sources import full_text, google_alerts, kakao, naver


def main():
    state = load_json(DATA / "state.json", {})
    status = load_json(DATA / "status.json", {})
    seen = load_json(DATA / "seen.json", {})
    events = load_json(DATA / "events.json", {})
    ig_events = load_json(DATA / "ig_events.json", {})   # PC가 올린 인스타 결과 (읽기만)

    process_feedback(state, status)

    items = []
    for kw in SEARCH_KEYWORDS:
        items += naver(kw)
        items += kakao(kw)
    items += google_alerts()

    now = time.time()
    cutoff = datetime.now(timezone.utc) - timedelta(days=MAX_AGE_DAYS)
    cands, keys = [], set()
    for it in items:
        key = norm_url(it["url"])
        if not key or key in seen or key in keys:
            continue
        keys.add(key)
        if (it["dt"] and it["dt"] < cutoff) or not prefilter(it["title"] + " " + it["snippet"]):
            seen[key] = now
            continue
        it["key"] = key
        cands.append(it)
    cands = cands[:MAX_ANALYZE_PER_RUN]   # 나머지는 다음 실행 때

    for it in cands:
        it["text"] = it["title"] + "\n" + full_text(it)

    all_events = {**events, **ig_events}
    fb_text, has_dislikes = feedback_examples(all_events, status)
    analyses = analyze(cands, state.setdefault("llm_usage", {}), fb_text)

    known = {ev["ekey"] for ev in all_events.values() if ev.get("ekey")}
    for it in cands:
        seen[it["key"]] = now
        a = analyses.get(it["key"])
        label = decide(a, has_dislikes) if a else rule_classify(it["text"])
        if not label:
            continue
        ev = build_event(it, a, label)
        if ev["ekey"] and ev["ekey"] in known:   # 같은 장터 다른 소개 글
            continue
        if ev["ekey"]:
            known.add(ev["ekey"])
        events[event_id(it["key"])] = ev

    pending = sorted([(eid, ev) for eid, ev in events.items() if not ev.get("notified")],
                     key=lambda x: x[1]["label"] != "ok")
    sent = 0
    for eid, ev in pending[:MAX_NOTIFY_PER_RUN]:
        if send(format_event(ev), buttons_for(eid, status.get(eid))):
            ev["notified"] = True
            sent += 1

    save_json(DATA / "seen.json", prune_seen(seen))
    save_json(DATA / "events.json", prune_events(events))
    save_json(DATA / "status.json", status)
    save_json(DATA / "state.json", state)
    print(f"수집 {len(items)} · 후보 {len(cands)} · LLM 분석 {len(analyses)} · 전송 {sent}")


if __name__ == "__main__":
    main()
