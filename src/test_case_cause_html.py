
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
    popup.locator("text=未准备诉状").first.click(timeout=3000)
    time.sleep(3)
    with open('screenshots/probe/after_click_no_complaint.html','w',encoding='utf-8') as f:
        f.write(popup.content())
    popup.screenshot(path='screenshots/probe/after_click_no_complaint.png')
    # also dump all visible texts
    texts = popup.evaluate("""() => {
        const out = [];
        for (const el of document.querySelectorAll('uni-text, uni-view, span, div, uni-label')) {
            const t = el.textContent && el.textContent.trim();
            if (t && t.length >= 2 && t.length <= 50) out.push({tag:el.tagName, cls:el.className, text:t});
        }
        return out;
    }""")
    print(json.dumps(texts, ensure_ascii=False, indent=2))
    browser.close()
