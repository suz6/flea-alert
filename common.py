"""설정 · 공통 유틸 · 판정 규칙"""
import hashlib
import html
import json
import os
import re
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).parent
DATA = ROOT / "data"
KST = timezone(timedelta(hours=9))

# ─────────────────────────────────────────────
# 1. 설정 (여기만 고치면 동작이 바뀝니다)
# ─────────────────────────────────────────────
INCLUDE_INCHEON = False      # 인천(송도·부평 등)도 받으려면 True
MAX_AGE_DAYS = 60            # 이보다 오래된 글은 무시
MAX_ANALYZE_PER_RUN = 60     # 한 번 실행에 LLM으로 읽을 최대 글 수
MAX_NOTIFY_PER_RUN = 25      # 한 번에 보낼 최대 알림 수 (남으면 다음 실행 때)
LLM_BATCH = 5                # LLM 1회 호출에 묶을 글 수
LLM_DAILY_LIMIT = int(os.environ.get("LLM_DAILY_LIMIT", "300"))
DIGEST_DEADLINE_DAYS = 14    # 주간 정리: 오늘부터 며칠 안에 마감되는 공고

SEARCH_KEYWORDS = [
    "벼룩시장 판매자 모집", "벼룩시장 참가자 모집",
    "나눔장터 판매자 모집", "나눔장터 참가 신청",
    "플리마켓 셀러 모집", "플리마켓 판매자 모집",
    "프리마켓 셀러 모집", "녹색장터 판매자 모집",
    "알뜰장터 참가자 모집", "중고장터 판매자 모집",
]

# 1차 거르기(느슨하게): 장터 단어 + 모집 단어가 둘 다 있어야 LLM에 넘김
MARKET_WORDS = ["벼룩시장", "나눔장터", "플리마켓", "프리마켓", "녹색장터", "알뜰장터",
                "아나바다", "중고장터", "되살림", "벼룩장터", "장터", "마켓"]
RECRUIT_WORDS = ["모집", "참가 신청", "참가신청", "판매 신청", "판매신청", "신청 접수",
                 "신청접수", "신청서", "구글폼", "forms.gle", "접수"]

# LLM을 못 쓸 때만 쓰는 예비 규칙
USED_OK_WORDS = ["중고", "누구나", "나눔", "제한없음", "제한 없음", "아나바다", "재사용",
                 "되살림", "개인 판매", "안 쓰는 물건", "안쓰는 물건"]
EXCLUDE_WORDS = ["핸드메이드만", "핸드메이드 한정", "사업자 한정", "사업자등록증",
                 "작가 모집", "창업마켓", "푸드트럭 모집", "공연팀", "입점 모집", "브랜드 모집"]

SEOUL = ["서울", "종로", "용산", "성동", "광진", "동대문", "중랑", "성북", "강북", "도봉",
         "노원", "은평", "서대문", "마포", "양천", "강서구", "구로", "금천", "영등포", "동작",
         "관악", "서초", "강남", "송파", "강동", "망원", "성수", "홍대", "연남", "합정",
         "잠실", "여의도", "뚝섬", "올림픽공원", "문래", "이태원", "서울숲", "청계천"]
GYEONGGI = ["경기", "수원", "성남", "분당", "판교", "고양", "일산", "용인", "부천", "안산",
            "안양", "평촌", "남양주", "화성", "동탄", "평택", "의정부", "시흥", "파주", "김포",
            "광명", "경기 광주", "광주시", "군포", "하남", "미사", "오산", "이천", "안성",
            "의왕", "양주", "구리", "포천", "여주", "동두천", "과천", "가평", "양평", "연천",
            "광교", "위례", "운정", "다산"]
INCHEON = ["인천", "송도", "부평", "계양", "연수구", "청라", "검단", "영종"]
OTHERS = ["부산", "대구", "광주광역시", "대전", "울산", "세종", "강원", "춘천", "원주",
          "충북", "청주", "충남", "천안", "전북", "전주", "전남", "경북", "포항", "경남",
          "창원", "제주"]

TARGET_REGIONS = SEOUL + GYEONGGI + (INCHEON if INCLUDE_INCHEON else [])
OTHER_REGIONS = OTHERS + ([] if INCLUDE_INCHEON else INCHEON)
ALLOWED_REGION_LABELS = {"서울", "경기"} | ({"인천"} if INCLUDE_INCHEON else set())


# ─────────────────────────────────────────────
# 2. .env 읽기 (PC 실행용)
# ─────────────────────────────────────────────
def _load_env():
    p = ROOT / ".env"
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"'))


_load_env()
LLM_DAILY_LIMIT = int(os.environ.get("LLM_DAILY_LIMIT", str(LLM_DAILY_LIMIT)))


# ─────────────────────────────────────────────
# 3. 유틸
# ─────────────────────────────────────────────
def clean(s):
    return html.unescape(re.sub(r"<[^>]+>", "", s or "")).strip()


def has_any(text, words):
    return any(w in text for w in words)


def today_kst():
    return datetime.now(KST).date()


def parse_date(s):
    try:
        return date.fromisoformat((s or "").strip()[:10])
    except ValueError:
        return None


def norm_url(url):
    url = (url or "").split("#")[0].rstrip("/")
    return re.sub(r"[?&](utm_[^&]+|igsh=[^&]+)", "", url)


def event_id(key):
    return hashlib.sha1(key.encode()).hexdigest()[:10]


def event_key(name, event_date):
    if not name or not event_date:
        return None
    return re.sub(r"[\W_]+", "", name).lower() + "|" + event_date


def load_json(path, default):
    path = Path(path)
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return default


def save_json(path, obj):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")


def prune_seen(seen, keep_days=150):
    cutoff = time.time() - keep_days * 86400
    return {k: v for k, v in seen.items() if v >= cutoff}


def prune_events(events, keep_days=120):
    t = today_kst()
    out = {}
    for eid, ev in events.items():
        last = parse_date(ev.get("event_date")) or parse_date(ev.get("deadline"))
        if last and last < t - timedelta(days=30):
            continue
        if time.time() - ev.get("found_at", time.time()) > keep_days * 86400:
            continue
        out[eid] = ev
    return out


# ─────────────────────────────────────────────
# 4. 판정
# ─────────────────────────────────────────────
def prefilter(text):
    if not has_any(text, MARKET_WORDS) or not has_any(text, RECRUIT_WORDS):
        return False
    return not (has_any(text, OTHER_REGIONS) and not has_any(text, TARGET_REGIONS))


def rule_classify(text):
    """LLM을 못 쓸 때 예비 판정"""
    in_region = has_any(text, TARGET_REGIONS)
    used_ok = has_any(text, USED_OK_WORDS)
    excluded = has_any(text, EXCLUDE_WORDS)
    if excluded and not used_ok:
        return None
    if used_ok and in_region and not excluded:
        return "ok"
    return "check"


def decide(a, use_fit=False):
    """LLM 분석 결과 → None(제외) / 'ok' / 'check'"""
    if not a.get("is_recruit"):
        return None
    region = a.get("region", "불명")
    if region not in ALLOWED_REGION_LABELS and region != "불명":
        return None
    seller = a.get("seller", "불명")
    if seller in ("사업자·전문셀러", "작가·핸드메이드", "대상제한"):
        return None
    used = a.get("used_goods", "불명")
    if used == "불가":
        return None
    t = today_kst()
    dl = parse_date(a.get("deadline"))
    ed = parse_date(a.get("event_date"))
    if (dl and dl < t) or (ed and ed < t):
        return None
    if use_fit and a.get("user_fit") == "낮음":
        return None
    if seller == "개인가능" and used == "가능" and region in ALLOWED_REGION_LABELS:
        return "ok"
    return "check"


def build_event(it, a, label):
    a = a or {}
    ev = {
        "label": label, "title": it["title"][:150], "url": it["url"],
        "source": it["source"], "date": it.get("date", ""),
        "name": a.get("market_name", ""), "summary": a.get("summary", ""),
        "region": a.get("region", ""), "place": a.get("place", ""),
        "event_date": a.get("event_date", ""), "deadline": a.get("deadline", ""),
        "fee": a.get("fee", ""), "apply_link": a.get("apply_link", ""),
        "seller": a.get("seller", ""), "used_goods": a.get("used_goods", ""),
        "item_note": a.get("item_note", ""), "resident_area": a.get("resident_area", ""),
        "snippet": "" if a else it.get("text", "")[:400],
        "llm": bool(a), "found_at": time.time(), "notified": False,
    }
    ev["ekey"] = event_key(ev["name"], ev["event_date"])
    return ev


def feedback_examples(all_events, status, prefs=(), n=8):
    """버튼·답장 기록과 사용자가 직접 보낸 기준 → LLM 프롬프트 문단"""
    likes, dislikes = [], []
    # 이유(답장)가 달린 기록을 먼저, 그다음 최신순
    for eid, st in sorted(status.items(), key=lambda x: (not x[1].get("note"), -x[1].get("at", 0))):
        ev, fb = all_events.get(eid), st.get("feedback")
        if not ev or fb not in ("like", "dislike"):
            continue
        desc = ev.get("summary") or ev.get("snippet", "")[:120]
        line = f"- {ev.get('name') or ev.get('title')}: {desc}"
        if st.get("note"):
            line += f" → 사용자 의견: {st['note']}"
        (likes if fb == "like" else dislikes).append(line)
    txt = ""
    if prefs:
        txt += ("\n[사용자가 직접 정한 기준] 아래 중 하나라도 해당하면 user_fit을 \"낮음\"으로 해.\n"
                + "\n".join(f"- {p}" for p in prefs) + "\n")
    if likes or dislikes:
        txt += ("\n[사용자 피드백 예시] 아래와 비슷한 정도로 user_fit을 판단해. "
                "'사용자 의견'은 이유이니 비슷한 이유에 해당하는 글도 같은 방향으로 판단해.\n")
        if likes:
            txt += "원했던 공고:\n" + "\n".join(likes[:n]) + "\n"
        if dislikes:
            txt += "원하지 않았던 공고:\n" + "\n".join(dislikes[:n]) + "\n"
    return txt, bool(dislikes or prefs)
