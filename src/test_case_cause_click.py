
import os, sys, time, json
sys.path.insert(0, 'src')
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright
from adapters.beijing_court import BeijingCourtAdapter
load_dotenv()

with sync_playwright() as p:
    adapter = BeijingCourtAdapter()
    browser = p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"])
    ctx = browser.new_context(viewport={"width": 1600, "height": 900})
    page = ctx.new_page()
    ok = adapter.login(page, {"username": os.getenv("BEIJING_COURT_USERNAME"), "password": os.getenv("BEIJING_COURT_PASSWORD")})
    if not ok: print('login failed'); browser.close(); sys.exit(1)
    popup = adapter.navigate_to_filing(page)
    adapter.fill_case_form(popup, {"court_name": "北京市海淀区人民法院"})
    popup.wait_for_selector("text=选择立案案由", timeout=10000)
    time.sleep(2)
    # try click 未准备诉状
    for txt in ["未准备诉状", "已准备诉状"]:
        try:
            popup.locator(f"text={txt}").first.click(timeout=3000)
            print(f"clicked {txt}")
            time.sleep(3)
            popup.screenshot(path=f"screenshots/probe/after_click_{txt}.png")
            html = popup.content()
            for key in ['请选择立案方式','未准备诉状','已准备诉状','选择案由','案由','合同纠纷','人格权纠纷','婚姻家庭纠纷']:
                print(key, 'YES' if key in html else 'NO')
            break
        except Exception as e:
            print(f"click {txt} err", e)
    browser.close()
