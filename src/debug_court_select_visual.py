#!/usr/bin/env python3
import os, sys, time, json
sys.path.insert(0, os.path.dirname(__file__))
from pathlib import Path
from playwright.sync_api import sync_playwright
from dotenv import load_dotenv
from utils.captcha_solver import CaptchaSolver
load_dotenv()

HEADLESS = False
SLOW_MO = 500
SAVE_DIR = Path("screenshots/probe")
SAVE_DIR.mkdir(parents=True, exist_ok=True)

def wait(t=1.0): time.sleep(t)

def click_text(page, text, timeout=5000):
    for fn in [lambda: page.get_by_text(text, exact=True).click(timeout=timeout),
               lambda: page.click(f"text={text}", timeout=timeout),
               lambda: page.evaluate("""(t) => { for (const el of document.querySelectorAll('*')) if (el.textContent && el.textContent.trim()===t){ el.click(); return true; } return false; }""", text)]:
        try: fn(); wait(0.5); return True
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

def find_xzfy(page, retries=5, delay=1.0):
    for i in range(retries):
        try:
            return page.evaluate("""() => {
                function walk(v) {
                    if (!v) return null;
                    const tag = v.$options && (v.$options.name || v.$options._componentTag || v.$options.__name);
                    if (tag === 'xzfy') return v;
                    for (const c of v.$children || []) { const r = walk(c); if (r) return r; }
                    return null;
                }
                const app = document.querySelector('uni-app');
                if (!app || !app.__vue__) return {err: 'no vue'};
                return walk(app.__vue__);
            }""") or {}
        except Exception as e:
            print('find_xzfy retry', i, e)
            time.sleep(delay)
    return {}

def main():
    username = os.getenv("BEIJING_COURT_USERNAME")
    password = os.getenv("BEIJING_COURT_PASSWORD")
    with sync_playwright() as p:
        browser = p.chromium.launch(channel='chrome', headless=HEADLESS, slow_mo=SLOW_MO, args=["--disable-blink-features=AutomationControlled"])
        ctx = browser.new_context(viewport={"width": 1600, "height": 900})
        page = ctx.new_page()
        if not login(page, username, password):
            print("LOGIN FAILED"); browser.close(); return

        click_text(page, "在线立案")
        wait(3)
        click_text(page, "我要立案")
        wait(3)

        # 在主页面先把省份切到北京，避免弹窗加载后切换导致页面重载
        print('set province on main page')
        page.evaluate("""() => {
            function findHeader(v) {
                if (!v) return null;
                const tag = v.$options && (v.$options.name || v.$options._componentTag || v.$options.__name);
                if (tag === 'commonHeader') return v;
                for (const c of v.$children || []) { const r = findHeader(c); if (r) return r; }
                return null;
            }
            const app = document.querySelector('uni-app').__vue__;
            const header = findHeader(app);
            if (header) {
                const idx = (header.provinces || []).indexOf('110000');
                header.currentAreaIndex = idx > 0 ? idx : 1;
                if (typeof header.updateHeaderStorage === 'function') header.updateHeaderStorage();
            }
            uni.setStorageSync('provinceId', '110000');
            return 'main province set';
        }""")
        wait(3)

        # trigger civil first instance
        item_info = page.evaluate("""() => {
            const items = document.querySelectorAll('.fd-children-item');
            let el = null;
            for (const item of items) if (item.textContent.includes('民事一审')) { el = item; break; }
            if (!el) return {err: 'no element'};
            let v = el.__vue__;
            while (v) {
                if (v.$options && (v.$options.name || v.$options._componentTag) === 'pagesWsla-pc-zxla-pick-case-type-index') {
                    const list = v.typeDataList || [];
                    for (const type of list) if (type.children) for (const child of type.children) if (child.name === '民事一审') return {item: child, typeName: type.name};
                    return {err: 'not found in typeDataList'};
                }
                v = v.$parent;
            }
            return {err: 'page comp not found'};
        }""")
        if not item_info or not item_info.get('item'):
            print('no item_info'); browser.close(); return
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
            return 'not found';
        }}""")
        popup = ctx.wait_for_event('page', timeout=30000)
        popup.wait_for_selector("text=选择受理法院", timeout=30000)
        print("popup ready", popup.url)
        try:
            popup.wait_for_load_state('networkidle', timeout=15000)
        except Exception:
            pass
        wait(5)

        # close 综治中心 popup if present
        for btn_text in ['关闭', '×']:
            try: popup.get_by_role('button', name=btn_text).click(timeout=3000); wait(0.5); break
            except Exception: pass
        wait(3)

        # set province to beijing
        x = find_xzfy(popup)
        print('before set', x.get('value'), x.get('citymc'), x.get('fyId') if x else None)
        popup.evaluate("""() => {
            function walk(v) {
                if (!v) return null;
                const tag = v.$options && (v.$options.name || v.$options._componentTag || v.$options.__name);
                if (tag === 'xzfy') return v;
                for (const c of v.$children || []) { const r = walk(c); if (r) return r; }
                return null;
            }
            function findHeader(v) {
                if (!v) return null;
                const tag = v.$options && (v.$options.name || v.$options._componentTag || v.$options.__name);
                if (tag === 'commonHeader') return v;
                for (const c of v.$children || []) { const r = findHeader(c); if (r) return r; }
                return null;
            }
            const app = document.querySelector('uni-app').__vue__;
            const header = findHeader(app);
            if (header) {
                const idx = (header.provinces || []).indexOf('110000');
                header.currentAreaIndex = idx > 0 ? idx : 1;
                if (typeof header.updateHeaderStorage === 'function') header.updateHeaderStorage();
            }
            const x = walk(app);
            if (x) {
                x.value = '110000';
                x.citymc = '北京市';
                x.currentIndex = 0;
                x.fyList = [];
                if (typeof x.getCityList === 'function') x.getCityList();
            }
            return 'set';
        }""")
        try:
            popup.wait_for_load_state('networkidle', timeout=10000)
        except Exception:
            pass
        try:
            popup.wait_for_selector("text=选择受理法院", timeout=20000)
        except Exception:
            pass
        wait(5)
        x = find_xzfy(popup)
        print('after set', x.get('value'), x.get('citymc'), x.get('fyId'), 'fyList len', len(x.get('fyList', [])))
        with open(SAVE_DIR / 'debug_fylist.json', 'w', encoding='utf-8') as f:
            json.dump(x.get('fyList', []), f, ensure_ascii=False, indent=2)
        popup.screenshot(path=str(SAVE_DIR / 'debug_01_after_beijing.png'), full_page=True)
        with open(SAVE_DIR / 'debug_01_after_beijing.html', 'w', encoding='utf-8') as f: f.write(popup.content())
        print('saved 01')

        # print all courts
        for fy in x.get('fyList', []):
            print(fy.get('value'), fy.get('text'))

        # method A: try to click haidian label
        target = "北京市海淀区人民法院"
        for sel in [f"uni-label:has-text('{target}')", f"text={target}", "xpath=//uni-label[.//span[contains(text(), '北京市海淀区人民法院')]]"]:
            try:
                print('trying selector', sel)
                popup.locator(sel).first.click(force=True, timeout=5000)
                wait(2)
                popup.screenshot(path=str(SAVE_DIR / 'debug_02_click_haidian.png'), full_page=True)
                with open(SAVE_DIR / 'debug_02_click_haidian.html', 'w', encoding='utf-8') as f: f.write(popup.content())
                x2 = find_xzfy(popup)
                print('after click', x2.get('fyId'), x2.get('fymc'))
                break
            except Exception as e:
                print('click failed', sel, e)

        # method B: directly set fyId via changeFy
        haidian = None
        for fy in x.get('fyList', []):
            if fy.get('text') == '北京市海淀区人民法院':
                haidian = fy.get('value'); break
        print('haidian value', haidian)
        if haidian:
            popup.evaluate(f"""() => {{
                function walk(v) {{
                    if (!v) return null;
                    const tag = v.$options && (v.$options.name || v.$options._componentTag || v.$options.__name);
                    if (tag === 'xzfy') return v;
                    for (const c of v.$children || []) {{ const r = walk(c); if (r) return r; }}
                    return null;
                }}
                const x = walk(document.querySelector('uni-app').__vue__);
                x.fyId = '{haidian}';
                x.fymc = '北京市海淀区人民法院';
                if (typeof x.changeFy === 'function') x.changeFy();
                x.$forceUpdate && x.$forceUpdate();
                return 'set haidian';
            }}""")
            wait(3)
            popup.screenshot(path=str(SAVE_DIR / 'debug_03_js_haidian.png'), full_page=True)
            with open(SAVE_DIR / 'debug_03_js_haidian.html', 'w', encoding='utf-8') as f: f.write(popup.content())
            x3 = find_xzfy(popup)
            print('after js', x3.get('fyId'), x3.get('fymc'))

        # click 本人申请
        click_text(popup, "本人申请")
        wait(1)
        popup.screenshot(path=str(SAVE_DIR / 'debug_04_agree.png'), full_page=True)
        with open(SAVE_DIR / 'debug_04_agree.html', 'w', encoding='utf-8') as f: f.write(popup.content())

        # click next
        try:
            popup.get_by_role('button', name='下一步').click(timeout=5000)
        except Exception:
            popup.click("text=下一步", timeout=5000)
        wait(3)
        popup.screenshot(path=str(SAVE_DIR / 'debug_05_after_next.png'), full_page=True)
        with open(SAVE_DIR / 'debug_05_after_next.html', 'w', encoding='utf-8') as f: f.write(popup.content())
        print('done, url', popup.url)
        wait(10)
        browser.close()

if __name__ == '__main__':
    main()
