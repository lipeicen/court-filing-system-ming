
import os, sys, time
sys.path.insert(0, 'src')
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright
from adapters.beijing_court import BeijingCourtAdapter
load_dotenv()

SAVE_DIR = 'screenshots/visual_upload'
os.makedirs(SAVE_DIR, exist_ok=True)

def snap(page, name):
    try:
        page.screenshot(path=f'{SAVE_DIR}/{name}.png', full_page=True)
        with open(f'{SAVE_DIR}/{name}.html','w',encoding='utf-8') as f:
            f.write(page.content())
    except Exception as e:
        print('snap err', e)

with sync_playwright() as p:
    adapter = BeijingCourtAdapter()
    browser = p.chromium.launch(
        headless=False,
        slow_mo=300,
        args=["--disable-blink-features=AutomationControlled", "--start-maximized"]
    )
    ctx = browser.new_context(viewport={"width": 1600, "height": 900})
    page = ctx.new_page()
    ok = adapter.login(page, {"username": os.getenv("BEIJING_COURT_USERNAME"), "password": os.getenv("BEIJING_COURT_PASSWORD")})
    if not ok: print('login failed'); browser.close(); sys.exit(1)
    popup = adapter.navigate_to_filing(page)
    adapter.fill_case_form(popup, {"court_name": "北京市海淀区人民法院", "metadata": {"case_cause": "买卖合同纠纷"}})
    time.sleep(3)
    snap(popup, '01_upload_page')
    print('最终URL', popup.url)
    # 找到第一个加号上传按钮
    target = popup.locator(".fd-file-container.fd-btn-add").first
    print('target count', target.count())
    # 点击并捕获 filechooser
    try:
        with popup.expect_event('filechooser') as fc_info:
            target.click(timeout=3000)
        fc = fc_info.value
        test_file = os.path.abspath(f'{SAVE_DIR}/test_material.png')
        fc.set_files(test_file)
        print('filechooser uploaded', test_file)
        time.sleep(3)
        snap(popup, '02_uploaded_filechooser')
    except Exception as e:
        print('filechooser err', e)
    # 查找 file input
    inputs = popup.query_selector_all("input[type='file']")
    print('file inputs after click', len(inputs))
    for i, inp in enumerate(inputs):
        print(i, inp.get_attribute('accept'), inp.get_attribute('id'), inp.get_attribute('class'))
    # 如果找到 input，直接 set_input_files
    if inputs:
        test_file = os.path.abspath(f'{SAVE_DIR}/test_material.png')
        inputs[0].set_input_files(test_file)
        print('uploaded via input', test_file)
        time.sleep(3)
        snap(popup, '03_uploaded_input')
    time.sleep(3)
    browser.close()
