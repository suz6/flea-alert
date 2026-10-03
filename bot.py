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
        # 같은 버튼 상태로 다시 그리기, 늦게 처리한 버튼 응답은 정상 상황이라 무시
        if not r.ok and not any(s in r.text for s in ("message is not modified", "query is too old")):
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


def apply_url(ev):
    """신청 링크가 도메인만 남은 경우(https://forms.gle 등) 원문 링크로 대체"""
    link = ev.get("apply_link") or ""
    return link if re.match(r"https?://[^/\s]+/\S", link) else ev["url"]


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
        if ev.get("apply_link") and apply_url(ev) != ev["url"]:
            lines.append(f"✍️ 신청: {e(apply_url(ev))}")
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


URL_RE = re.compile(r"🔗 (\S+)")
LIKE_WORDS = ["좋", "관심", "괜찮", "굿", "good", "👍", "👌"]
MAX_PREFS = 30


def _reply(chat_id, text, to=None):
    payload = {"chat_id": chat_id, "text": text}
    if to:
        payload["reply_parameters"] = {"message_id": to, "allow_sending_without_reply": True}
    call("sendMessage", **payload)


def liked_list(status, html_mode=False):
    """👍 누른 공고 (신청함·지난 공고 제외), 마감일 → 행사일 순"""
    from common import DATA, load_json, parse_date, today_kst
    events = {**load_json(DATA / "events.json", {}), **load_json(DATA / "ig_events.json", {})}
    t = today_kst()
    rows = []
    for eid, st in status.items():
        ev = events.get(eid)
        if not ev or st.get("feedback") != "like" or st.get("applied"):
            continue
        dl, ed = parse_date(ev.get("deadline")), parse_date(ev.get("event_date"))
        if (dl and dl < t) or (ed and ed < t):
            continue
        rows.append((dl or ed or t.replace(year=t.year + 1), ev))
    rows.sort(key=lambda r: r[0])
    e = html.escape if html_mode else (lambda x: x)
    lines = []
    for _, ev in rows:
        when = (f"⏰ {fmt_day(ev['deadline'])} 마감" if ev.get("deadline")
                else f"📅 행사 {fmt_day(ev['event_date'])}" if ev.get("event_date") else "⏰ 마감 미상")
        name = e(ev.get("name") or ev["title"][:40])
        lines.append(f"⭐ {when} | " + (f"<b>{name}</b>" if html_mode else name))
        lines.append(f"    {e(apply_url(ev))}")
    if html_mode:
        return lines
    if not lines:
        return "⭐ 관심 공고가 없어요. 마음에 드는 알림에 👍를 눌러 주세요."
    return "⭐ 관심 공고 (신청하면 📝 버튼을 눌러 주세요)\n" + "\n".join(lines)


def _handle_text(msg, state, status):
    """답장 = 그 공고에 대한 이유 / 그냥 메시지 = 항상 적용할 기준"""
    from common import event_id, norm_url
    text = (msg.get("text") or "").strip()
    chat, mid = msg["chat"]["id"], msg["message_id"]
    if not text or text.startswith("/"):
        return
    prefs = state.setdefault("prefs", [])
    replied = msg.get("reply_to_message") or {}
    m = URL_RE.search(replied.get("text") or "")
    if m:
        eid = event_id(norm_url(m.group(1)))
        st = status.setdefault(eid, {})
        st["feedback"] = "like" if any(w in text.lower() for w in LIKE_WORDS) else "dislike"
        st["note"] = text[:200]
        st["at"] = time.time()
        if replied.get("message_id"):
            call("editMessageReplyMarkup", chat_id=chat, message_id=replied["message_id"],
                 reply_markup={"inline_keyboard": buttons_for(eid, st)})
        mark = "👍 관심" if st["feedback"] == "like" else "👎 해당 없음"
        _reply(chat, f"{mark}으로 기록했어요. 이유: {st['note']}", mid)
    elif text.replace(" ", "") == "관심목록":
        _reply(chat, liked_list(status))
    elif text.replace(" ", "") == "기준목록":
        body = "\n".join(f"{i}. {p}" for i, p in enumerate(prefs, 1)) or "(저장된 기준 없음)"
        _reply(chat, "📋 저장된 기준\n" + body + "\n\n지우기: 기준 삭제 번호")
    elif re.fullmatch(r"기준\s*삭제\s*\d+", text):
        n = int(re.search(r"\d+", text).group())
        if 1 <= n <= len(prefs):
            _reply(chat, f"🗑 지웠어요: {prefs.pop(n - 1)}", mid)
        else:
            _reply(chat, f"{n}번 기준이 없어요. '기준 목록'으로 번호를 확인해 주세요.", mid)
    elif m is None and replied:
        _reply(chat, "공고 알림에 답장해 주셔야 그 공고의 이유로 기록돼요.", mid)
    else:
        prefs.append(text[:200])
        del prefs[:-MAX_PREFS]
        _reply(chat, f"📌 기준으로 저장했어요 ({len(prefs)}번): {text[:200]}\n"
                     "목록 보기: 기준 목록 / 지우기: 기준 삭제 번호", mid)


def process_feedback(state, status):
    """버튼·답장·메시지 기록 가져오기 (GitHub Actions에서만 실행)"""
    _, chat_id = _token()
    res = call("getUpdates", offset=state.get("tg_offset", 0), timeout=0,
               allowed_updates=["callback_query", "message"])
    if not res or not res.get("ok"):
        return
    pressed = set()   # 반응이 늦어 연달아 누른 같은 버튼은 한 번으로
    for u in res.get("result", []):
        state["tg_offset"] = u["update_id"] + 1
        msg = u.get("message")
        if msg and str(msg.get("chat", {}).get("id")) == str(chat_id):
            _handle_text(msg, state, status)
            continue
        cq = u.get("callback_query")
        if not cq:
            continue
        msg = cq.get("message") or {}
        if str(msg.get("chat", {}).get("id")) != str(chat_id):
            continue
        action, _, eid = cq.get("data", "").partition(":")
        if action not in LABELS or (action, eid) in pressed:
            continue
        pressed.add((action, eid))
        st = status.setdefault(eid, {})
        if action == "applied":
            st["applied"] = not st.get("applied")
        else:
            st["feedback"] = action   # 👍/👎는 눌러도 꺼지지 않음 (바꾸려면 반대 버튼)
        st["at"] = time.time()
        call("editMessageReplyMarkup", chat_id=msg["chat"]["id"], message_id=msg["message_id"],
             reply_markup={"inline_keyboard": buttons_for(eid, st)})
        call("answerCallbackQuery", callback_query_id=cq["id"], text=LABELS[action])
