#!/usr/bin/env python3
import os, sys, time, json
sys.path.insert(0, os.path.dirname(__file__))
from pathlib import Path
from playwright.sync_api import sync_playwright
from dotenv import load_dotenv
from utils.captcha_solver import CaptchaSolver
load_dotenv()

SAVE_DIR = Path("screenshots/probe")
SAVE_DIR.mkdir(parents=True, exist_ok=True)

def wait(t=1.0): time.sleep(t)

def click_text(page, text, timeout=8000, exact=False):
    for fn in [lambda: page.get_by_text(text, exact=exact).click(timeout=timeout),
               lambda: page.click(f"text={text}", timeout=timeout),
               lambda: page.evaluate("""(t) => { for (const el of document.querySelectorAll('*')) if (el.textContent && el.textContent.trim()===t){ el.click(); return true; } return false; }""", text)]:
        try: fn(); wait(0.5); return True
        except Exception: pass
    return False

def login(page, username, password, max_retry=3):
    for attempt in range(1, max_retry+1):
        page.goto("https://zxfw.court.gov.cn/zxfw/#/pagesGrxx/pc/login/index", wait_until="domcontentloaded")
        wait(4)
        click_text(page, "律师用户")
        wait(1)
        click_text(page, "密码登录")
        wait(1)
        try: page.wait_for_selector("input[type='password']", timeout=5000)
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
        wait(6)
        content = page.content()
        if "在线立案" in content and "密码登录" not in content:
            return True
    return False

def main():
    username = '13723715831'
    password = 'HU1234pp'
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, args=["--disable-blink-features=AutomationControlled"])
        ctx = browser.new_context(viewport={"width": 1600, "height": 900})
        page = ctx.new_page()
        login(page, username, password)
        click_text(page, "在线立案")
        wait(3)
        click_text(page, "我要立案")
        wait(3)
        click_text(page, "民事一审")
        wait(4)
        # Try to inspect parent component picker event binding
        info = page.evaluate("""() => {
            const app = document.querySelector('uni-app');
            const v = app.__vue__;
            function find(v) {
                if (!v) return null;
                const tag = v.$options && (v.$options.name || v.$options._componentTag || v.$options.__name);
                if (tag === 'pagesWsla-pc-zxla-pick-case-type-index') return v;
                for (const c of v.$children || []) { const r = find(c); if (r) return r; }
                return null;
            }
            const comp = find(v);
            if (!comp) return {err: 'no parent'};
            // inspect $vnode for listeners on uni-picker
            const picker = comp.$children.find(c => (c.$options && (c.$options.name || c.$options._componentTag || c.$options.__name)) === 'uni-picker') || comp.$refs.picker;
            return {
                comp_keys: Object.keys(comp.$data),
                picker: picker ? {methods: Object.keys(picker.$options.methods || {}), data: Object.keys(picker.$data || {})} : null,
                listeners: comp.$vnode && comp.$vnode.componentOptions && comp.$vnode.componentOptions.listeners ? Object.keys(comp.$vnode.componentOptions.listeners) : null,
                elm_events: comp._events ? Object.keys(comp._events) : null
            };
        }""")
        with open(SAVE_DIR/'parent_picker_info.json','w',encoding='utf-8') as f:
            json.dump(info, f, ensure_ascii=False, indent=2)
        print(json.dumps(info, ensure_ascii=False, indent=2)[:3000])
        # Try to use picker._pickerViewChange to select index 1
        res = page.evaluate("""() => {
            const el = document.querySelector('uni-picker');
            const v = el && el.__vue__;
            if (!v) return {err: 'no vue'};
            try {
                // set selected index to 1 (北京市), mode=selector, rangeArray length
                if (typeof v._pickerViewChange === 'function') {
                    v._pickerViewChange({detail: {value: [1]}});
                }
                return {ok: true, value: v.value, valueArray: v.valueArray};
            } catch(e) { return {err: e.message}; }
        }""")
        print('pickerViewChange', res)
        wait(1)
        # Try to call _change
        res2 = page.evaluate("""() => {
            const el = document.querySelector('uni-picker');
            const v = el && el.__vue__;
            if (!v) return {err: 'no vue'};
            try { v._change(); return {ok: true}; } catch(e) { return {err: e.message}; }
        }""")
        print('change', res2)
        wait(3)
        page.screenshot(path=str(SAVE_DIR/'after_picker_change.png'))
        print('url', page.url)
        # Check if province changed
        text = page.evaluate("""() => {
            const el = document.querySelector('.uni-input');
            return el ? el.textContent.trim() : '';
        }""")
        print('input text', text)
        wait(10)
        browser.close()

if __name__ == '__main__':
    main()
