import os, sys, time, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright
from adapters.beijing_court import BeijingCourtAdapter
load_dotenv()

SAVE_DIR = 'screenshots/visual_import'
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
    snap(popup, '01_upload_page')
    print('url', popup.url)

    # Click 引入常用材料 first button
    import_btns = popup.locator("text=+ 引入常用材料")
    print('import buttons', import_btns.count())
    if import_btns.count() > 0:
        import_btns.first.click(timeout=5000)
        print('clicked import first')
        time.sleep(3)
        snap(popup, '02_import_dialog')
    browser.close()
