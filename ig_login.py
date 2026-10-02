"""인스타 부계정 로그인 세션 저장 (처음 한 번, 세션 만료 시 다시 실행)"""
from playwright.sync_api import sync_playwright

from common import ROOT

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    ctx = browser.new_context(locale="ko-KR")
    page = ctx.new_page()
    page.goto("https://www.instagram.com/accounts/login/")
    input("브라우저에서 '부계정'으로 로그인을 마친 뒤 여기서 엔터를 누르세요... ")
    ctx.storage_state(path=str(ROOT / "ig_state.json"))
    print("저장 완료: ig_state.json")
    browser.close()
