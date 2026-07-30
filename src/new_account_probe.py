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
    username = '13723715831'
    password = 'HU1234pp'
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, args=["--disable-blink-features=AutomationControlled"])
        ctx = browser.new_context(viewport={"width": 1600, "height": 900})
        page = ctx.new_page()
        page.on('response', lambda response: print('RESP', response.status, response.url[:220]) if any(k in response.url for k in ['ajlx','court','city','fy','login','captcha']) else None)
        login_ok = login(page, username, password)
        print('login ok', login_ok)
        if not login_ok:
            with open(SAVE_DIR / 'login_fail_new.html', 'w', encoding='utf-8') as f: f.write(page.content())
            page.screenshot(path=str(SAVE_DIR / 'login_fail_new.png'), full_page=True)
            browser.close(); return
        # direct navigate to wsla
        url = "https://zxfw.court.gov.cn/zxfw/index.html#/pagesWsla/common/wsla/index?ajlx=1501_000001-0301&ajlxMc=民事一审"
        page.goto(url, wait_until="networkidle")
        wait(8)
        # init and inspect province/city
        page.evaluate("""() => {
            const app = document.querySelector('uni-app'); const vue = app.__vue__;
            function find(v) { if (!v) return null; const tag = v.$options && (v.$options.name || v.$options._componentTag || v.$options.__name); if (tag === 'xzfy') return v; for (const c of v.$children || []) { const r = find(c); if (r) return r; } return null; }
            const v = find(vue); v.init();
        }""")
        for _ in range(30):
            wait(0.5)
            state = page.evaluate("""() => {
                const app = document.querySelector('uni-app'); const vue = app.__vue__;
                function find(v) { if (!v) return null; const tag = v.$options && (v.$options.name || v.$options._componentTag || v.$options.__name); if (tag === 'xzfy') return v; for (const c of v.$children || []) { const r = find(c); if (r) return r; } return null; }
                const v = find(vue);
                return {value: v.value, cityListLen: v.cityList ? v.cityList.length : -1, fyListLen: v.fyList ? v.fyList.length : -1};
            }""")
            if state['cityListLen'] > 0:
                print('loaded', state); break
        else:
            print('city not loaded')
        with open(SAVE_DIR / 'new_account_wsla.html', 'w', encoding='utf-8') as f: f.write(page.content())
        page.screenshot(path=str(SAVE_DIR / 'new_account_wsla.png'), full_page=True)
        # dump full state
        full_state = page.evaluate("""() => {
            const app = document.querySelector('uni-app'); const vue = app.__vue__;
            function find(v) { if (!v) return null; const tag = v.$options && (v.$options.name || v.$options._componentTag || v.$options.__name); if (tag === 'xzfy') return v; for (const c of v.$children || []) { const r = find(c); if (r) return r; } return null; }
            const v = find(vue);
            return {value: v.value, citymc: v.citymc, cityList: v.cityList.map(c=> ({text: c.citymc, value: c.cityid})), fyList: v.fyList.map(f=> ({text: f.text, value: f.value})), ajlxList: v.ajlxList.map(a=> ({text: a.text, value: a.value})), sqrSf: v.sqrSf, selecedAjlx: v.selecedAjlx, fyId: v.fyId};
        }""")
        print(json.dumps(full_state, ensure_ascii=False, indent=2))
        with open(SAVE_DIR / 'new_account_wsla_state.json', 'w', encoding='utf-8') as f:
            json.dump(full_state, f, ensure_ascii=False, indent=2)
        wait(15)
        browser.close()

if __name__ == '__main__':
    main()
