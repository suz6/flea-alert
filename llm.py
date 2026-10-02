"""Gemini 무료 티어로 공고 본문 읽고 항목 추출"""
import json
import os
import time

import requests

from common import LLM_BATCH, LLM_DAILY_LIMIT, today_kst

MODEL = os.environ.get("GEMINI_MODEL") or "gemini-flash-lite-latest"
URL = "https://generativelanguage.googleapis.com/v1beta/models/{}:generateContent"

PROMPT = """너는 벼룩시장·나눔장터·플리마켓 '판매자 모집' 공고를 분류하는 도우미야.
사용자는 '개인'으로 '중고물품'을 팔기 위해 판매자로 참가하려고 해. 품목은 특별히 정하지 않았어.
사업자가 필요하거나 전문 셀러·브랜드·작가를 찾는 마켓은 원하지 않아.
오늘 날짜: {today}

각 글을 읽고 JSON 배열만 출력해 (설명 금지).
[{{"id": 글 번호(정수),
  "is_recruit": 판매자·셀러·참가자 '모집' 공고면 true. 행사 후기, 방문 홍보, 구매자 안내, 지난 행사 회고는 false,
  "market_name": 장터 이름(모르면 ""),
  "seller": "개인가능" | "주민한정" | "사업자·전문셀러" | "작가·핸드메이드" | "대상제한" | "불명",
  "resident_area": seller가 "주민한정"일 때 대상 지역(예: "여주시", "서울 강서구 화곡1동"), 아니면 "",
  "used_goods": "가능" | "불가" | "제한" | "불명",
  "item_note": 품목 제한 내용 짧게(없으면 ""),
  "region": "서울" | "경기" | "인천" | "기타" | "불명",
  "place": 장소 짧게,
  "event_date": 행사 첫날 YYYY-MM-DD(연도가 없으면 오늘 기준 가장 가까운 미래, 모르면 ""),
  "deadline": 신청 마감 YYYY-MM-DD(모르면 ""),
  "fee": 참가비(예: "무료", "1만원", 모르면 ""),
  "apply_link": 신청 링크(없으면 ""),
  "user_fit": "높음" | "보통" | "낮음" (피드백 예시가 없으면 "보통"),
  "summary": 한 줄 요약}}]

판단 기준:
- 사업자등록증 필요, 브랜드·전문 셀러·입점업체 모집 → seller "사업자·전문셀러"
- 핸드메이드·창작품·작가만 → seller "작가·핸드메이드"
- 판매자가 어린이·청소년·학생만(어린이장터 등), 특정 단지 입주민·회원·조합원만, 파트너·협력기관만 → seller "대상제한" (사용자는 성인 일반인)
- 성인도 신청할 수 있지만 특정 시·구·동 주민(관내 거주자, ○○구민 등)만 가능 → seller "주민한정" + resident_area
- 중고, 나눔, 누구나, 카테고리 제한 없음 → used_goods "가능"
- 푸드·체험·공연 분야만 모집 → used_goods "불가"
- 판매 품목이 수공예품·농산품·먹거리·지역 특산품처럼 중고물품이 아닌 것뿐이면 → used_goods "불가" ('벼룩시장'이라는 이름만 보고 "가능"이라 하지 말 것)
- 곤충·반려동물·식물·특정 취미 용품처럼 특수한 주제 전문 장터 → used_goods "불가" + item_note
- 의류·도서·장난감·생활용품 등 일반 가정 중고품 중 일부만 가능하면 → used_goods "제한" + item_note
- region은 본문 주소뿐 아니라 글 주소(URL)와 카페·블로그 이름도 단서로 써 (예: cafe.daum.net/daegumam → 대구 → "기타")
{feedback}
[글 목록]
{items}"""


def analyze(items, usage, feedback=""):
    """items: [{'key','title','text'}] → {key: 분석결과}"""
    key = os.environ.get("GEMINI_API_KEY")
    results = {}
    if not key or not items:
        return results
    for i in range(0, len(items), LLM_BATCH):
        day = today_kst().isoformat()
        if usage.get("day") != day:
            usage.update(day=day, count=0)
        if usage["count"] >= LLM_DAILY_LIMIT:
            print("오늘 LLM 한도 도달 → 예비 규칙 사용")
            break
        batch = items[i:i + LLM_BATCH]
        listing = "\n\n".join(
            f"[글 {n}] 제목: {it['title']}\n주소: {it.get('url', '')} ({it.get('source', '')})\n"
            f"본문: {it['text'][:2500]}" for n, it in enumerate(batch))
        prompt = PROMPT.format(today=day, feedback=feedback, items=listing)
        try:
            r = requests.post(
                URL.format(MODEL),
                headers={"x-goog-api-key": key, "Content-Type": "application/json"},
                json={"contents": [{"role": "user", "parts": [{"text": prompt}]}],
                      "generationConfig": {"temperature": 0, "responseMimeType": "application/json"}},
                timeout=90)
            usage["count"] += 1
            if r.status_code == 429:
                print("Gemini 무료 한도 초과 → 예비 규칙 사용")
                break
            r.raise_for_status()
            parts = r.json()["candidates"][0]["content"]["parts"]
            data = json.loads("".join(p.get("text", "") for p in parts if not p.get("thought")))
            if isinstance(data, dict):
                data = data.get("items") or [data]
            for a in data:
                n = int(a.get("id", -1))
                if 0 <= n < len(batch):
                    results[batch[n]["key"]] = a
        except Exception as ex:
            print("LLM 오류:", ex)
        time.sleep(7)   # 분당 호출 한도 여유
    return results
