# 벼룩시장 · 나눔장터 · 플리마켓 판매자 모집 알림 (v2)

서울·경기에서 **개인이 중고물품 판매자로 신청할 수 있는 장터**를 찾아 텔레그램으로 보냅니다.
사업자 필요, 전문 셀러·브랜드·작가 모집, 중고 불가 공고는 걸러냅니다.

## 동작 방식

```
수집 → 1차 거르기(단어) → 원문 본문 읽기 → Gemini가 판단·항목 추출 → 텔레그램
```

| 파일 | 실행 위치 | 주기 | 하는 일 |
|---|---|---|---|
| main.py | GitHub Actions | 1시간마다 | 네이버·다음·구글 알리미 수집, 버튼 기록 반영 |
| digest.py | GitHub Actions | 금요일 19시 | 14일 안에 마감되는 공고 정리 |
| ig_collect.py | 내 PC | 하루 1~2회 | 인스타 키워드 검색 |

**알림 버튼**
- 👍 관심 / 👎 해당 없음 → 쌓이면 Gemini가 "이 사용자가 싫어하는 유형"을 참고해서 비슷한 건 걸러요
- 📝 신청함 → 금요일 정리에서 빠져요

버튼 기록은 다음 정시 실행 때 반영돼요(최대 1시간).

**Gemini가 뽑는 항목:** 판매자 자격, 중고 가능 여부·품목 제한, 지역, 행사일, 신청 마감, 참가비, 신청 링크
무료 한도를 넘거나 키가 없으면 단어 규칙으로 자동 전환돼요.

---

## 1. 키 발급

**텔레그램 봇**
1. `@BotFather` → `/newbot` → 토큰 → `TELEGRAM_BOT_TOKEN`
2. 만든 봇에게 아무 메시지 보내기
3. 브라우저로 `https://api.telegram.org/bot<토큰>/getUpdates` → `"chat":{"id":숫자` → `TELEGRAM_CHAT_ID`

**Gemini API (무료)**
aistudio.google.com → Get API key → `GEMINI_API_KEY` (카드 등록 필요 없음, 결제 연결하지 마세요)

**네이버 검색 API**
⚠️ **현재 비추천** — 2026-07-31 개발자센터 신규 발급 종료, NAVER API HUB(네이버 클라우드)는 결제수단 등록 필수·향후 유료 예정, 2026-09-07 약관에서 검색 결과의 AI 입력 금지(이 프로그램은 Gemini에 넣음). 키가 없으면 네이버는 자동으로 건너뜀. 쓰려면: console.ncloud.com → NAVER API HUB 이용 신청 → Application 등록(검색) → `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET`

**카카오(다음) 검색 API**
developers.kakao.com → 앱 만들기 → REST API 키 → `KAKAO_REST_KEY`

**구글 알리미 (선택)**
google.com/alerts → 키워드 입력 → 옵션 표시 → 수신 위치 **RSS 피드** → RSS 링크 복사 (여러 개는 쉼표) → `GOOGLE_ALERT_FEEDS`

## 2. GitHub 세팅

1. 새 저장소에 이 폴더 전체 업로드 (**공개 저장소 추천**: Actions 무제한 무료)
   - 비공개로 하려면 `.github/workflows/collect.yml` 의 cron을 `"17 */2 * * *"`(2시간마다)로 바꾸세요
2. Settings → Secrets and variables → Actions → 위 키 7개 등록
3. Actions 탭 → `flea-market-alert` → **Run workflow** 로 첫 실행 확인

공개 저장소여도 키는 Secrets에 있어서 노출되지 않아요. `data/` 폴더에는 공개 게시물 정보와 버튼 기록만 저장돼요.

## 3. 인스타그램 (내 PC, Windows)

> ⚠️ 비공식 방식이라 계정이 제한될 수 있어요. **반드시 부계정**으로 하세요.

```bash
git clone <내 저장소 주소>
cd <폴더>
pip install -r requirements-ig.txt
playwright install chromium
copy .env.example .env      # 메모장으로 열어 텔레그램·Gemini 값 입력
python ig_login.py          # 브라우저가 뜨면 부계정 로그인 후 엔터
run_ig.bat                  # 테스트 실행 (결과는 ig_log.txt)
```

`git push` 가 되려면 PC에서 GitHub 로그인이 한 번 되어 있어야 해요.

**자동 실행:** 작업 스케줄러 → 기본 작업 만들기 → 매일 → 프로그램에 `run_ig.bat` 지정. 하루 두 번이면 트리거를 하나 더 추가.

`ig_state.json`(로그인 세션)은 `.gitignore`로 막혀 있어 업로드되지 않아요.

## 4. 조정 (`common.py` 상단)

- `INCLUDE_INCHEON = True` → 인천도 받기
- `SEARCH_KEYWORDS` → 네이버·다음 검색어 / 인스타는 `ig_collect.py` 의 `IG_KEYWORDS`
- `DIGEST_DEADLINE_DAYS` → 금요일 정리에 넣을 마감 범위 (기본 14일)
- 판단 기준 문장은 `llm.py` 의 `PROMPT` 에서 바꿀 수 있어요

## 알려진 한계

- 네이버·다음 **카페 글은 로그인 없이 원문을 못 봐서** 요약문으로만 판단해요 → ⚠️가 많을 수 있어요
- 인스타는 화면 구조가 바뀌면 수정이 필요해요
- Gemini 무료 티어는 입력 데이터가 구글 모델 개선에 쓰일 수 있어요 (공개 게시물만 보내요)
