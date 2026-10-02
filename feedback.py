"""GitHub Actions(10분마다): 버튼 기록만 빠르게 반영 (수집·LLM 없음)"""
from bot import process_feedback
from common import DATA, load_json, save_json


def main():
    state = load_json(DATA / "state.json", {})
    status = load_json(DATA / "status.json", {})
    process_feedback(state, status)
    save_json(DATA / "status.json", status)
    save_json(DATA / "state.json", state)
    print("버튼 기록 반영 완료")


if __name__ == "__main__":
    main()
