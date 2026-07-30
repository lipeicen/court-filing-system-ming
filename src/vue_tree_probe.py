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

def click_text(page, text, timeout=8000):
    for fn in [lambda: page.get_by_text(text, exact=True).click(timeout=timeout),
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
    username = '13149930995'
    password = 'lijiayu123'
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, args=["--disable-blink-features=AutomationControlled"])
        ctx = browser.new_context(viewport={"width": 1600, "height": 900})
        page = ctx.new_page()
        login(page, username, password)
        click_text(page, "在线立案")
        wait(3)
        click_text(page, "我要立案")
        wait(3)
        # find and traverse page vue tree
        tree = page.evaluate("""() => {
            const app = document.querySelector('uni-app');
            if (!app || !app.__vue__) return {err: 'no app'};
            const vue = app.__vue__;
            function walk(v, depth=0) {
                if (!v) return null;
                const tag = v.$options && (v.$options.name || v.$options._componentTag || v.$options.__name);
                const dataKeys = Object.keys(v.$data || v).slice(0,30);
                const children = (v.$children || []).map(c => walk(c, depth+1)).filter(Boolean);
                return {tag, dataKeys, depth, children};
            }
            return walk(vue);
        }""")
        with open(SAVE_DIR / 'vue_tree.json', 'w', encoding='utf-8') as f:
            json.dump(tree, f, ensure_ascii=False, indent=2)
        print(json.dumps(tree, ensure_ascii=False, indent=2)[:3000])
        # Click 民事一审 then look for selected data
        click_text(page, "民事一审")
        wait(3)
        page_state = page.evaluate("""() => {
            const app = document.querySelector('uni-app');
            if (!app || !app.__vue__) return {err: 'no app'};
            const vue = app.__vue__;
            function findPage(v) {
                if (!v) return null;
                const tag = v.$options && (v.$options.name || v.$options._componentTag || v.$options.__name);
                if (tag === 'pagesWsla-pc-zxla-pick-case-type-index') return v;
                for (const c of v.$children || []) { const r = findPage(c); if (r) return r; }
                return null;
            }
            const v = findPage(vue);
            if (!v) return {err: 'page not found'};
            return {
                selected: v.selected, selectedType: v.selectedType, selectedChild: v.selectedChild,
                typeDataList: v.typeDataList.map(t => ({name: t.name, children: (t.children||[]).map(c=>c.name)}))
            };
        }""")
        print(json.dumps(page_state, ensure_ascii=False, indent=2)[:3000])
        with open(SAVE_DIR / 'page_state.json', 'w', encoding='utf-8') as f:
            json.dump(page_state, f, ensure_ascii=False, indent=2)
        # Try to click the next button by selecting DOM element with class fd-com-btn or similar
        wait(10)
        browser.close()

if __name__ == '__main__':
    main()
