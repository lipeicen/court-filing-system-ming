
import os, sys, time, json
sys.path.insert(0, os.path.dirname(__file__))
from pathlib import Path
from playwright.sync_api import sync_playwright
from dotenv import load_dotenv
from utils.captcha_solver import CaptchaSolver
load_dotenv()

HEADLESS = False
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
        print('login attempt', attempt)
        page.goto("https://zxfw.court.gov.cn/zxfw/#/pagesGrxx/pc/login/index", wait_until="domcontentloaded")
        wait(3)
        click_text(page, "律师用户")
        wait(0.5)
        click_text(page, "密码登录")
        wait(0.5)
        try:
            page.wait_for_selector("input[type='password']", timeout=5000)
        except Exception:
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
            print('login ok'); return True
        print('login failed, url', page.url)
    return False

def main():
    username = os.getenv("BEIJING_COURT_USERNAME")
    password = os.getenv("BEIJING_COURT_PASSWORD")
    with sync_playwright() as p:
        browser = p.chromium.launch(channel='chrome', headless=HEADLESS, args=["--disable-blink-features=AutomationControlled"])
        ctx = browser.new_context(viewport={"width": 1600, "height": 900})
        page = ctx.new_page()
        if not login(page, username, password):
            print("LOGIN FAILED"); browser.close(); return
        click_text(page, "在线立案")
        wait(3)
        click_text(page, "我要立案")
        wait(3)
        item_info = page.evaluate("""() => {
            const items = document.querySelectorAll('.fd-children-item');
            let el = null;
            for (const item of items) if (item.textContent.includes('民事一审')) { el = item; break; }
            if (!el) return {err: 'no element'};
            let v = el.__vue__;
            while (v) {
                if (v.$options && (v.$options.name || v.$options._componentTag) === 'pagesWsla-pc-zxla-pick-case-type-index') {
                    const list = v.typeDataList || [];
                    for (const type of list) {
                        if (type.children) {
                            for (const child of type.children) {
                                if (child.name === '民事一审') return {item: child, typeName: type.name};
                            }
                        }
                    }
                    return {err: 'not found in typeDataList'};
                }
                v = v.$parent;
            }
            return {err: 'page comp not found'};
        }""")
        if item_info and item_info.get('item'):
            item_json = json.dumps(item_info['item'], ensure_ascii=False)
            page.evaluate(f"""() => {{
                const target = {item_json};
                const items = document.querySelectorAll('.fd-children-item');
                let el = null;
                for (const item of items) if (item.textContent.includes('民事一审')) {{ el = item; break; }}
                let v = el.__vue__;
                while (v) {{
                    if (v.$options && (v.$options.name || v.$options._componentTag) === 'pagesWsla-pc-zxla-pick-case-type-index') {{
                        v.toZxla(target);
                        return 'called';
                    }}
                    v = v.$parent;
                }}
                return 'not found';
            }}""")
            popup = ctx.wait_for_event('page', timeout=30000)
            popup.wait_for_selector("text=选择受理法院", timeout=30000)
            print("popup ready", popup.url)
            wait(3)
            # close 综治中心 popup if present
            for btn_text in ['关闭', '×']:
                try:
                    popup.get_by_role('button', name=btn_text).click(timeout=3000)
                    wait(0.5)
                    break
                except Exception:
                    pass
            try:
                popup.evaluate("""() => {
                    const all = document.querySelectorAll('*');
                    for (const el of all) if (el.textContent && el.textContent.includes('综治中心')) {
                        let p = el; while (p && p !== document.body) { if (p.classList && (p.classList.contains('uni-popup') || p.classList.contains('el-dialog'))) { const close = p.querySelector('.uni-popup__close, .el-dialog__close, .close'); if (close) close.click(); else p.style.display='none'; break; } p = p.parentElement; }
                    }
                }""")
                wait(1)
            except Exception:
                pass
            wait(2)
            # select Haidian court
            popup.evaluate("""() => {
                function findXzfy(v) {
                    if (!v) return null;
                    const tag = v.$options && (v.$options.name || v.$options._componentTag || v.$options.__name);
                    if (tag === 'xzfy') return v;
                    for (const c of v.$children || []) { const r = findXzfy(c); if (r) return r; }
                    return null;
                }
                const x = findXzfy(document.querySelector('uni-app').__vue__);
                if (x) {
                    x.value = '110000'; x.citymc = '北京市'; x.currentIndex = 0; x.fyList = [];
                    x.getCityList && x.getCityList();
                    return 'set beijing';
                }
                return 'no xzfy';
            }""")
            wait(5)
            popup.evaluate("""() => {
                function findXzfy(v) {
                    if (!v) return null;
                    const tag = v.$options && (v.$options.name || v.$options._componentTag || v.$options.__name);
                    if (tag === 'xzfy') return v;
                    for (const c of v.$children || []) { const r = findXzfy(c); if (r) return r; }
                    return null;
                }
                const x = findXzfy(document.querySelector('uni-app').__vue__);
                if (x) {
                    x.fyId = '6'; x.fymc = '北京市海淀区人民法院';
                    x.changeFy && x.changeFy();
                    return 'changeFy called';
                }
                return 'no xzfy';
            }""")
            wait(5)
            html = popup.content()
            with open(SAVE_DIR / 'test_court_select.html','w',encoding='utf-8') as f: f.write(html)
            popup.screenshot(path=str(SAVE_DIR / 'test_court_select.png'), full_page=True)
            print("saved")
            # click next step; popup closes and original page navigates
            try:
                popup.get_by_role('button', name='下一步').click(timeout=5000)
                wait(0.5)
            except Exception:
                popup.click("text=下一步", timeout=5000)
                wait(0.5)
            wait(2)
            # wait for popup to close and original page to show next step
            try:
                popup.wait_for_event('close', timeout=10000)
            except Exception:
                pass
            wait(5)
            page.wait_for_selector("text=阅读须知", timeout=20000)
            page.screenshot(path=str(SAVE_DIR / 'test_court_select_step2.png'), full_page=True)
            with open(SAVE_DIR / 'test_court_select_step2.html','w',encoding='utf-8') as f: f.write(page.content())
            print("step2 saved")
        browser.close()

if __name__ == '__main__':
    main()
