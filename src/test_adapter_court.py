
import os, sys, time
sys.path.insert(0, 'src')
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright
from adapters.beijing_court import BeijingCourtAdapter
load_dotenv()

def main():
    adapter = BeijingCourtAdapter()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"])
        ctx = browser.new_context(viewport={"width": 1600, "height": 900})
        page = ctx.new_page()
        ok = adapter.login(page, {"username": os.getenv("BEIJING_COURT_USERNAME"), "password": os.getenv("BEIJING_COURT_PASSWORD")})
        if not ok:
            print('login failed'); browser.close(); return
        popup = adapter.navigate_to_filing(page)
        adapter.fill_case_form(popup, {"court_name": "北京市海淀区人民法院"})
        time.sleep(5)
        print('popup url', popup.url)
        adapter._save_state(popup, "test_select_court_end")
        browser.close()

if __name__ == '__main__':
    main()
