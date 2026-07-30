#!/usr/bin/env python3
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
        browser = p.chromium.launch(headless=HEADLESS, args=["--disable-blink-features=AutomationControlled"])
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
            click_text(popup, "杭州市")
            wait(2)
            # Get xzfy component data
            xzfy = popup.evaluate("""() => {
                function walk(v) {
                    if (!v) return null;
                    if (v.$options && (v.$options.name || v.$options._componentTag) === 'xzfy') return v;
                    for (const c of v.$children || []) {
                        const r = walk(c);
                        if (r) return r;
                    }
                    return null;
                }
                const root = document.querySelector('uni-app').__vue__;
                const v = walk(root);
                if (!v) return {err: 'xzfy not found'};
                const data = v.$data;
                return {
                    cityList: (data.cityList || []).map(c => ({name: c.name, id: c.id})),
                    fyList: (data.fyList || []).map(f => ({name: f.name, id: f.id})),
                    sqrLxArray: (data.sqrLxArray || []).map(x => ({name: x.name, value: x.value})),
                    currentIndex: data.currentIndex,
                    index: data.index,
                    modeIndex: data.modeIndex,
                    value: data.value,
                    chooseValue: data.chooseValue,
                    fyId: data.fyId,
                    checked: data.checked,
                    range: (data.range || []).slice(0,10),
                };
            }""")
            with open(SAVE_DIR / 'xzfy_data.json', 'w', encoding='utf-8') as f:
                json.dump(xzfy, f, ensure_ascii=False, indent=2)
            print('xzfy_data saved')
        browser.close()

if __name__ == '__main__':
    main()
