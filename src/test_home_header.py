
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
    for fn in [lambda: page.get_by_text(text, exact=True).click(timeout=timeout),
               lambda: page.click(f"text={text}", timeout=timeout),
               lambda: page.evaluate("""(text) => { const all = document.querySelectorAll('*'); for (const el of all) if (el.textContent && el.textContent.trim() === text) { el.click(); return true; } return false; }""", text)]:
        try: fn(); wait(0.5); return True
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
    # inspect commonHeader methods on home page
    info = page.evaluate("""() => {
        function walk(v) {
            if (!v) return null;
            const tag = v.$options && (v.$options.name || v.$options._componentTag || v.$options.__name);
            if (tag === 'commonHeader') return v;
            for (const c of v.$children || []) { const r = walk(c); if (r) return r; }
            return null;
        }
        const h = walk(document.querySelector('uni-app').__vue__);
        return {
            methods: Object.keys(h.$options.methods || {}),
            data: h._data ? Object.keys(h._data) : []
        };
    }""")
    with open(SAVE_DIR / 'home_header_methods.json','w',encoding='utf-8') as f:
        json.dump(info, f, ensure_ascii=False, indent=2)
    print('saved', info.keys())
    browser.close()
