
import os, sys, time, json
sys.path.insert(0, os.path.dirname(__file__))
from pathlib import Path
from playwright.sync_api import sync_playwright
from dotenv import load_dotenv
from utils.captcha_solver import CaptchaSolver
load_dotenv()

HEADLESS = True
SAVE_DIR = Path("screenshots/probe")

def wait(t=1.0): time.sleep(t)

def click_text(page, text, timeout=5000):
    try:
        page.get_by_text(text, exact=True).click(timeout=timeout)
        wait(0.5); return True
    except Exception: pass
    try:
        page.click(f"text={text}", timeout=timeout)
        wait(0.5); return True
    except Exception: pass
    try:
        page.evaluate("""(text) => {
            const all = document.querySelectorAll('*');
            for (const el of all) if (el.textContent && el.textContent.trim() === text) { el.click(); return true; }
            return false;
        }""", text)
        wait(0.5); return True
    except Exception: pass
    return False

def login(page, username, password, max_retry=3):
    for attempt in range(1, max_retry+1):
        page.goto("https://zxfw.court.gov.cn/zxfw/#/pagesGrxx/pc/login/index", wait_until="domcontentloaded")
        wait(3)
        click_text(page, "律师用户")
        click_text(page, "密码登录")
        wait(1)
        inputs = page.query_selector_all(".uni-input-input")
        if len(inputs) >= 2:
            inputs[0].fill(username); inputs[1].fill(password)
        if len(inputs) >= 3:
            imgs = page.query_selector_all("img")
            if imgs:
                imgs[0].screenshot(path=str(SAVE_DIR / "captcha.png"))
                with open(SAVE_DIR / "captcha.png", 'rb') as f: b = f.read()
                code = CaptchaSolver().solve_image_captcha(b)
                inputs[2].fill(code)
        for sel in [".fd-login-btn", "button:has-text('登录')", ".login-btn"]:
            try: page.click(sel, timeout=3000); break
            except Exception: pass
        wait(5)
        content = page.content()
        if "在线立案" in content and "密码登录" not in content:
            return True
    return False

with sync_playwright() as p:
    browser = p.chromium.launch(headless=HEADLESS, args=["--disable-blink-features=AutomationControlled"])
    ctx = browser.new_context(viewport={"width": 1600, "height": 900})
    page = ctx.new_page()
    login(page, os.getenv("BEIJING_COURT_USERNAME"), os.getenv("BEIJING_COURT_PASSWORD"))
    click_text(page, "在线立案")
    wait(3)
    click_text(page, "我要立案")
    wait(3)
    item_info = page.evaluate("""() => {
        const items = document.querySelectorAll('.fd-children-item');
        let el = null;
        for (const item of items) if (item.textContent.includes('民事一审')) { el = item; break; }
        let v = el.__vue__;
        while (v) {
            if (v.$options && (v.$options.name || v.$options._componentTag) === 'pagesWsla-pc-zxla-pick-case-type-index') {
                const list = v.typeDataList || [];
                for (const type of list) {
                    if (type.children) {
                        for (const child of type.children) {
                            if (child.name === '民事一审') return {item: child};
                        }
                    }
                }
            }
            v = v.$parent;
        }
        return {err: 'not found'};
    }""")
    item_json = json.dumps(item_info['item'], ensure_ascii=False)
    page.evaluate(f"""() => {{
        const target = {item_json};
        const items = document.querySelectorAll('.fd-children-item');
        let el = null;
        for (const item of items) if (item.textContent.includes('民事一审')) {{ el = item; break; }}
        let v = el.__vue__;
        while (v) {{
            if (v.$options && (v.$options.name || v.$options._componentTag) === 'pagesWsla-pc-zxla-pick-case-type-index') {{
                v.toZxla(target); return 'called';
            }}
            v = v.$parent;
        }}
    }}""")
    popup = ctx.wait_for_event('page', timeout=30000)
    popup.wait_for_selector("text=选择受理法院", timeout=30000)
    print("popup url", popup.url)

    # 设置省份为北京
    popup.evaluate("""() => {
        uni.setStorageSync('provinceId', '110000');
        const app = document.querySelector('uni-app');
        if (!app) return 'no app';
        const root = app.__vue__;
        function find(v) {
            if (!v) return null;
            const tag = v.$options && (v.$options.name || v.$options._componentTag || v.$options.__name);
            if (tag === 'pagesWsla-common-wsla-index') return v;
            for (const c of v.$children || []) { const r = find(c); if (r) return r; }
            return null;
        }
        const comp = find(root);
        if (comp) {
            if (typeof comp.getListData === 'function') { comp.getListData(); return 'getListData called'; }
            if (comp.$options.methods && comp.$options.methods.getListData) { comp.$options.methods.getListData.call(comp); return 'method called'; }
            return 'no getListData';
        }
        return 'comp not found';
    }""")
    wait(3)

    # 尝试点击省份选择器
    click_text(popup, "最高")
    wait(2)
    click_text(popup, "北京市")
    wait(2)
    popup.screenshot(path=str(SAVE_DIR / 'court_select_after_beijing.png'), full_page=True)
    with open(SAVE_DIR / 'court_select_after_beijing.html','w',encoding='utf-8') as f: f.write(popup.content())
    print('saved')
    browser.close()
