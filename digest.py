"""매주 금요일 저녁: 마감 임박 정리"""
import html
from datetime import timedelta

from bot import fmt_day, process_feedback, send
from common import DATA, DIGEST_DEADLINE_DAYS, load_json, parse_date, save_json, today_kst


def main():
    state = load_json(DATA / "state.json", {})
    status = load_json(DATA / "status.json", {})
    events = {**load_json(DATA / "events.json", {}), **load_json(DATA / "ig_events.json", {})}
    process_feedback(state, status)

    t = today_kst()
    horizon = t + timedelta(days=DIGEST_DEADLINE_DAYS)
    rows = []
    for eid, ev in events.items():
        st = status.get(eid, {})
        if st.get("applied") or st.get("feedback") == "dislike" or not ev.get("label"):
            continue
        dl, ed = parse_date(ev.get("deadline")), parse_date(ev.get("event_date"))
        if dl:
            if t <= dl <= horizon:
                rows.append((dl, 0, ev))
        elif ed and t <= ed <= t + timedelta(days=30):
            rows.append((ed, 1, ev))   # 마감일 미상 → 행사일 기준
    rows.sort(key=lambda r: (r[1], r[0]))

    e = html.escape
    lines = [f"🗓 <b>마감 임박 정리</b> ({t.month}/{t.day} 기준, {DIGEST_DEADLINE_DAYS}일 이내)", ""]
    if not rows:
        lines.append("이번 주는 마감 임박 공고가 없어요.")
    undated_header = False
    for _, undated, ev in rows:
        if undated and not undated_header:
            lines += ["", "<b>마감일 미상 · 행사 30일 이내</b>"]
            undated_header = True
        mark = "✅" if ev["label"] == "ok" else "⚠️"
        when = f"⏰ {fmt_day(ev['deadline'])} 마감" if not undated else f"📅 행사 {fmt_day(ev['event_date'])}"
        name = e(ev.get("name") or ev["title"][:40])
        extra = " · ".join(x for x in [ev.get("place"), ev.get("fee")] if x)
        lines.append(f"{mark} {when} | <b>{name}</b>" + (f" — {e(extra)}" if extra else ""))
        lines.append(f"    {e(ev.get('apply_link') or ev['url'])}")

    chunk = ""
    for line in lines:
        if len(chunk) + len(line) > 3500:
            send(chunk)
            chunk = ""
        chunk += line + "\n"
    if chunk.strip():
        send(chunk)
    save_json(DATA / "status.json", status)
    save_json(DATA / "state.json", state)


if __name__ == "__main__":
    main()
