"""텔레그램: 전송 · 버튼 · 피드백 수집"""
import html
import os
import re
import time

import requests

DATE_RE = re.compile(r"\d{1,2}\s*월\s*\d{1,2}\s*일|\b\d{1,2}[./]\d{1,2}\b")
WEEK = "월화수목금토일"


def _token():
    return os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")


def call(method, **payload):
    token, _ = _token()
    if not token:
        return None
    for _ in range(3):
        try:
            r = requests.post(f"https://api.telegram.org/bot{token}/{method}", json=payload, timeout=20)
        except requests.RequestException as ex:
            print("텔레그램 연결 오류:", ex)
            time.sleep(3)
            continue
        if r.status_code == 429:
            time.sleep(r.json().get("parameters", {}).get("retry_after", 5) + 1)
            continue
        if not r.ok:
            print("텔레그램 오류:", method, r.text[:200])
        return r.json()
    return None


def send(text, buttons=None):
    token, chat_id = _token()
    if not token or not chat_id:
        print("[텔레그램 미설정 · 미리보기]\n" + text + "\n")
        return True
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML",
               "disable_web_page_preview": True}
    if buttons:
        payload["reply_markup"] = {"inline_keyboard": buttons}
    res = call("sendMessage", **payload)
    time.sleep(1.2)
    return bool(res and res.get("ok"))


def buttons_for(eid, st=None):
    st = st or {}
    fb = st.get("feedback")
    return [
        [{"text": "👍 관심" + (" ✔" if fb == "like" else ""), "callback_data": f"like:{eid}"},
         {"text": "👎 해당 없음" + (" ✔" if fb == "dislike" else ""), "callback_data": f"dislike:{eid}"}],
        [{"text": "📝 신청함" + (" ✔" if st.get("applied") else ""), "callback_data": f"applied:{eid}"}],
    ]


def fmt_day(s):
    from common import parse_date
    d = parse_date(s)
    return f"{d.month}/{d.day}({WEEK[d.weekday()]})" if d else ""


def format_event(ev):
    e = html.escape
    head = "✅ <b>신청 가능해 보여요</b>" if ev["label"] == "ok" else "⚠️ <b>확인 필요</b>"
    lines = [head, f"<b>{e(ev.get('name') or ev['title'])}</b>"]
    if ev.get("llm"):
        if ev.get("summary"):
            lines.append(e(ev["summary"]))
        info = []
        if ev.get("region") or ev.get("place"):
            info.append("📍 " + e(" ".join(x for x in [ev.get("region"), ev.get("place")] if x and x != "불명")))
        if ev.get("event_date"):
            info.append("📅 행사 " + fmt_day(ev["event_date"]))
        info.append("⏰ 마감 " + (fmt_day(ev["deadline"]) or "미상"))
        if ev.get("fee"):
            info.append("💰 " + e(ev["fee"]))
        lines += ["", "\n".join(info)]
        if ev.get("seller") == "주민한정":
            lines.append(f"🏠 <b>{e(ev.get('resident_area') or '지역')} 주민만 신청 가능</b>")
        lines.append(f"🧾 자격: {e(ev.get('seller') or '불명')} · 중고: {e(ev.get('used_goods') or '불명')}"
                     + (f" ({e(ev['item_note'])})" if ev.get("item_note") else ""))
        if ev.get("apply_link"):
            lines.append(f"✍️ 신청: {e(ev['apply_link'])}")
    else:
        body = ev.get("snippet", "")
        lines += ["", e(body[:400] + ("…" if len(body) > 400 else ""))]
        dates = []
        for m in DATE_RE.findall(ev["title"] + " " + body):
            m = re.sub(r"\s+", "", m)
            if m not in dates:
                dates.append(m)
        if dates:
            lines.append("📅 본문 속 날짜: " + ", ".join(dates[:6]))
    meta = ev["source"] + (f" · {ev['date']}" if ev.get("date") else "")
    lines += ["", f"🔗 {e(ev['url'])}", f"<i>{e(meta)}</i>"]
    return "\n".join(lines)


LABELS = {"like": "👍 관심으로 기록했어요", "dislike": "👎 앞으로 비슷한 건 덜 보낼게요",
          "applied": "📝 신청함으로 표시했어요 (주간 정리에서 빠져요)"}


def process_feedback(state, status):
    """버튼 누른 기록 가져오기 (GitHub Actions에서만 실행)"""
    _, chat_id = _token()
    res = call("getUpdates", offset=state.get("tg_offset", 0), timeout=0,
               allowed_updates=["callback_query"])
    if not res or not res.get("ok"):
        return
    for u in res.get("result", []):
        state["tg_offset"] = u["update_id"] + 1
        cq = u.get("callback_query")
        if not cq:
            continue
        msg = cq.get("message") or {}
        if str(msg.get("chat", {}).get("id")) != str(chat_id):
            continue
        action, _, eid = cq.get("data", "").partition(":")
        if action not in LABELS:
            continue
        st = status.setdefault(eid, {})
        if action == "applied":
            st["applied"] = not st.get("applied")
        else:
            st["feedback"] = None if st.get("feedback") == action else action
        st["at"] = time.time()
        call("editMessageReplyMarkup", chat_id=msg["chat"]["id"], message_id=msg["message_id"],
             reply_markup={"inline_keyboard": buttons_for(eid, st)})
        call("answerCallbackQuery", callback_query_id=cq["id"], text=LABELS[action])
