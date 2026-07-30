
import os, sys, time, json
sys.path.insert(0, 'src')
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright
from adapters.beijing_court import BeijingCourtAdapter
load_dotenv()

SAVE_DIR = 'screenshots/visual'
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
    adapter.fill_case_form(popup, {"court_name": "北京市海淀区人民法院"})
    time.sleep(2)
    # 关闭弹窗后，选择立案方式
    for btn in ["不选择要素式立案", "不体验智能识别要素式立案服务"]:
        try:
            loc = popup.locator("uni-button").filter(has_text=btn)
            if loc.count() and loc.is_visible():
                loc.click(timeout=3000)
                time.sleep(2)
        except Exception: pass
    snap(popup, '07_popup_closed')
    # 选择立案方式
    popup.locator("text=未准备诉状").first.click(timeout=3000)
    time.sleep(3)
    snap(popup, '08_case_mode')
    # 案由选择
    popup.locator(".uni-data-tree-input, .uni-data-tree, .input-value").first.click(timeout=3000)
    time.sleep(3)
    snap(popup, '09_tree_open')
    inp = popup.locator("input.fd-search-input, .fd-search-input input, .uni-input-input").first
    inp.fill("买卖合同纠纷")
    inp.press("Enter")
    time.sleep(3)
    snap(popup, '10_search_result')
    popup.locator("text=买卖合同纠纷").first.click(timeout=3000)
    time.sleep(2)
    snap(popup, '11_cause_selected')
    popup.locator("text=下一步").first.click(timeout=5000)
    time.sleep(5)
    snap(popup, '12_after_cause')
    # 上传材料页
    popup.wait_for_selector("text=上传诉讼材料", timeout=10000)
    snap(popup, '13_upload_page')
    print('最终URL', popup.url)
    # 查找所有上传 input
    inputs = popup.query_selector_all("input[type='file']")
    print('file inputs count', len(inputs))
    for i, inp in enumerate(inputs):
        print(i, inp.get_attribute('accept'), inp.get_attribute('id'), inp.get_attribute('class'))
    # 尝试上传一个测试文件到第一个 input
    if inputs:
        test_file = os.path.abspath('screenshots/visual/test_upload.txt')
        with open(test_file, 'w', encoding='utf-8') as f:
            f.write('测试材料内容')
        inputs[0].set_input_files(test_file)
        print('uploaded', test_file)
        time.sleep(5)
        snap(popup, '14_uploaded')
    time.sleep(3)
    browser.close()
