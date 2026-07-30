
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
    # 点击第一个加号区域（当事人身份证明）
    try:
        popup.locator("text=当事人身份证明").first.click(timeout=3000)
        print('clicked 当事人身份证明 text')
    except Exception as e:
        print('click text err', e)
    time.sleep(2)
    snap(popup, '02_after_click_text')
    # 尝试点击加号虚线框
    try:
        # find the plus icon after 当事人身份证明
        all = popup.query_selector_all('.fd-upload, .fd-upload-box, .uni-uploader__file, .uni-uploader__input, .uni-icon, .uni-icon-plusempty, .uni-icon-plus, .plus-icon, .upload-icon')
        print('upload elements', len(all))
        for i, el in enumerate(all[:10]):
            print(i, el.tag_name, el.get_attribute('class'), el.text_content()[:50])
        if all:
            all[0].click()
            print('clicked first upload element')
    except Exception as e:
        print('click upload err', e)
    time.sleep(3)
    snap(popup, '03_after_click_plus')
    # 查找 file input
    inputs = popup.query_selector_all("input[type='file']")
    print('file inputs', len(inputs))
    for i, inp in enumerate(inputs):
        print(i, inp.get_attribute('accept'), inp.get_attribute('id'), inp.get_attribute('class'))
    # 尝试用 Playwright filechooser
    if not inputs:
        try:
            with popup.expect_filechooser(timeout=5000) as fc_info:
                popup.locator("text=当事人身份证明").first.click(timeout=3000)
            fc = fc_info.value
            test_file = os.path.abspath(f'{SAVE_DIR}/test_id.txt')
            with open(test_file, 'w', encoding='utf-8') as f:
                f.write('当事人身份证明测试材料')
            fc.set_files(test_file)
            print('filechooser uploaded', test_file)
            time.sleep(3)
            snap(popup, '04_filechooser_uploaded')
        except Exception as e:
            print('filechooser err', e)
    time.sleep(3)
    browser.close()
