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
        print('login ok, url', page.url)
        click_text(page, "在线立案")
        wait(3)
        print('after 在线立案 url', page.url)
        click_text(page, "我要立案")
        wait(3)
        print('after 我要立案 url', page.url)
        # Capture vue component on main page
        state = page.evaluate("""() => {
            const app = document.querySelector('uni-app');
            if (!app || !app.__vue__) return {err: 'no app'};
            const vue = app.__vue__;
            function walk(v) {
                if (!v) return null;
                const tag = v.$options && (v.$options.name || v.$options._componentTag);
                if (tag) return {tag: tag, keys: Object.keys(v.$data || v).slice(0,20)};
                for (const c of v.$children || []) { const r = walk(c); if (r) return r; }
                return null;
            }
            return walk(vue);
        }""")
        print('main page vue', state)
        click_text(page, "民事一审")
        wait(5)
        print('after 民事一审 url', page.url)
        # Try to find xzfy component on page now
        state = page.evaluate("""() => {
            const app = document.querySelector('uni-app');
            if (!app || !app.__vue__) return {err: 'no app'};
            const vue = app.__vue__;
            function walk(v) {
                if (!v) return null;
                const tag = v.$options && (v.$options.name || v.$options._componentTag);
                if (tag === 'xzfy') {
                    return {
                        tag: tag,
                        value: v.value, citymc: v.citymc, cityList: v.cityList.map(c=> c.text || c.value),
                        fyListLen: v.fyList.length,
                        ajlxListLen: v.ajlxList.length,
                        sqrSf: v.sqrSf,
                        sqrSfList: v.sqrSfList.map(s=> ({text: s.text, value: s.value})),
                        pcSqrLx: v.pcSqrLx,
                        pcSqrLxList: v.pcSqrLxList.map(s=> ({text: s.text, value: s.value})),
                        selecedAjlx: v.selecedAjlx,
                        fyId: v.fyId
                    };
                }
                for (const c of v.$children || []) { const r = walk(c); if (r) return r; }
                return null;
            }
            return walk(vue);
        }""")
        print('xzfy state', json.dumps(state, ensure_ascii=False, indent=2))
        with open(SAVE_DIR / 'main_xzfy_state.json', 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        with open(SAVE_DIR / 'after_civil_click.html', 'w', encoding='utf-8') as f:
            f.write(page.content())
        page.screenshot(path=str(SAVE_DIR / 'after_civil_click.png'), full_page=True)
        wait(10)
        browser.close()

if __name__ == '__main__':
    main()
