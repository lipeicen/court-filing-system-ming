import os, sys, time, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright
from adapters.beijing_court import BeijingCourtAdapter
load_dotenv()

SAVE_DIR = 'screenshots/visual_party'
os.makedirs(SAVE_DIR, exist_ok=True)

def snap(page, name):
    try:
        page.screenshot(path=f'{SAVE_DIR}/{name}.png', full_page=True)
        with open(f'{SAVE_DIR}/{name}.html','w',encoding='utf-8') as f:
            f.write(page.content())
        print(f'snap {name}')
    except Exception as e:
        print('snap err', e)

with sync_playwright() as p:
    adapter = BeijingCourtAdapter()
    browser = p.chromium.launch(
        headless=False,
        args=["--disable-blink-features=AutomationControlled", "--start-maximized"]
    )
    ctx = browser.new_context(viewport={"width": 1600, "height": 900})
    page = ctx.new_page()
    ok = adapter.login(page, {"username": os.getenv("BEIJING_COURT_USERNAME"), "password": os.getenv("BEIJING_COURT_PASSWORD")})
    if not ok:
        print('login failed')
        browser.close()
        sys.exit(1)
    popup = adapter.navigate_to_filing(page)
    adapter.fill_case_form(popup, {"court_name": "北京市海淀区人民法院", "metadata": {"case_cause": "民间借贷纠纷"}})
    print('after fill_case_form url', popup.url)
    snap(popup, '01_upload_page')

    # Upload dummy files to required sections using filechooser on .fd-file-container.fd-btn-add
    dummy = os.path.abspath(os.path.join(os.path.dirname(__file__), 'src', 'documents', 'civil_complaint.png'))
    print('dummy file', dummy, os.path.exists(dummy))
    buttons = popup.locator('.fd-file-container.fd-btn-add')
    print('add buttons count', buttons.count())
    for i in range(min(buttons.count(), 3)):
        try:
            with popup.expect_event('filechooser', timeout=5000) as fc_info:
                buttons.nth(i).click(timeout=3000)
            fc = fc_info.value
            fc.set_files(dummy)
            print(f'uploaded to button {i}')
            time.sleep(2)
        except Exception as e:
            print(f'button {i} upload err', e)
    snap(popup, '02_uploaded')

    # click next
    popup.evaluate("""() => {
        const btns = document.querySelectorAll('uni-button, button');
        for (let i = btns.length - 1; i >= 0; i--) {
            const t = btns[i].innerText || btns[i].textContent || '';
            if (t.includes('下一步')) { btns[i].click(); return 'clicked ' + t; }
        }
        return 'no next';
    }""")
    time.sleep(5)
    snap(popup, '03_party_form_initial')
    print('url', popup.url)
    browser.close()
