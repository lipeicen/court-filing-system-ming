import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright
load_dotenv()

SAVE_DIR = 'screenshots/auth_test'
os.makedirs(SAVE_DIR, exist_ok=True)

root = os.path.dirname(__file__)
state_path = os.path.abspath(os.path.join(root, 'test_data', 'auth_state.json'))
print('state path', state_path, os.path.exists(state_path))

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False, args=["--disable-blink-features=AutomationControlled", "--start-maximized"])
    ctx = browser.new_context(
        viewport={"width": 1600, "height": 900},
        storage_state=state_path if os.path.exists(state_path) else None
    )
    page = ctx.new_page()
    page.goto("https://zxfw.court.gov.cn/zxfw/#/pagesWsla/pc/zxla/pick-case-type", wait_until="domcontentloaded")
    time.sleep(5)
    try:
        page.screenshot(path=f'{SAVE_DIR}/pick_case_type.png', full_page=True)
        with open(f'{SAVE_DIR}/pick_case_type.html','w',encoding='utf-8') as f:
            f.write(page.content())
    except Exception as e:
        print('screenshot err', e)
    print('url', page.url)
    content = page.content()
    print('has 在线立案', '在线立案' in content)
    print('has 登录', '登录' in content)
    print('has 律师', '律师' in content)
    browser.close()
