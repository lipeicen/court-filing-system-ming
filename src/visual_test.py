
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
    print('可视化窗口已打开，开始登录...')
    ok = adapter.login(page, {"username": os.getenv("BEIJING_COURT_USERNAME"), "password": os.getenv("BEIJING_COURT_PASSWORD")})
    if not ok: print('login failed'); browser.close(); sys.exit(1)
    snap(page, '01_login')
    print('登录成功，进入在线立案')
    popup = adapter.navigate_to_filing(page)
    snap(popup, '02_court_select')
    print('已打开法院选择页')
    adapter._set_xzfy_beijing(popup)
    snap(popup, '03_beijing_set')
    adapter._click_court_card(popup, "北京市海淀区人民法院")
    snap(popup, '04_haidian_selected')
    print('已选择海淀法院')
    # scroll to bottom where 本人申请 is located
    popup.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    time.sleep(1)
    snap(popup, '04b_scrolled')
    # select 本人申请
    try:
        popup.locator("text=本人申请").first.click(timeout=3000)
        print('选择本人申请')
    except Exception as e:
        print('本人申请 click err', e)
    time.sleep(1)
    snap(popup, '04c_self_applied')
    # click next manually visible
    try:
        popup.locator("text=下一步").first.click(timeout=5000)
        print('点击下一步')
    except Exception as e:
        print('下一步 click err', e)
    time.sleep(3)
    snap(popup, '05_after_next')
    print('法院选择完成，进入须知')
    # 阅读须知
    popup.wait_for_selector("text=立案须知", timeout=10000)
    for agree_text in ["已阅读同意立案须知内容", "已阅读同意", "已阅读并同意"]:
        try:
            popup.locator(f"text={agree_text}").first.click(timeout=2000)
            print('勾选', agree_text)
            break
        except Exception: pass
    popup.locator("uni-button").filter(has_text="下一步").click(timeout=5000)
    time.sleep(3)
    snap(popup, '06_notice_next')
    # 弹窗
    for btn in ["不选择要素式立案", "不体验智能识别要素式立案服务"]:
        try:
            loc = popup.locator("uni-button").filter(has_text=btn)
            if loc.count() and loc.is_visible():
                loc.click(timeout=3000)
                print('关闭弹窗', btn)
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
    # 搜索买卖合同纠纷
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
    snap(popup, '12_final')
    print('最终URL', popup.url)
    time.sleep(3)
    browser.close()
