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
        login(page, username, password)
        # go to pick case type and click 民事一审 with real user gesture to open popup
        click_text(page, "在线立案")
        wait(3)
        click_text(page, "我要立案")
        wait(3)
        click_text(page, "民事一审")
        wait(5)
        # Maybe a popup is blocked? Let's see if any new page. If none, we are on same page. Just capture all pages and current state.
        print('pages', [pg.url for pg in ctx.pages])
        # Click the province selector if visible. Try to find "浙江省" on the page and click it to see dropdown.
        # Let's first find any elements with text containing 浙江 or 省份.
        els = page.query_selector_all('*')
        for el in els:
            try:
                txt = el.inner_text()
                if txt and ('浙江省' in txt or '选择省份' in txt or '省份' in txt):
                    print('el text', txt[:50], 'class', el.get_attribute('class'))
            except Exception:
                pass
        # Save screenshot and html
        with open(SAVE_DIR / 'manual_pick.html', 'w', encoding='utf-8') as f: f.write(page.content())
        page.screenshot(path=str(SAVE_DIR / 'manual_pick.png'), full_page=True)
        # Try clicking 浙江省 to see dropdown
        click_text(page, "浙江省")
        wait(2)
        page.screenshot(path=str(SAVE_DIR / 'manual_pick_after_zj.png'), full_page=True)
        # List all visible text content that looks like province
        print('visible provinces:')
        for el in page.query_selector_all('*'):
            try:
                txt = el.inner_text()
                if txt and len(txt) <= 10 and ('省' in txt or '市' in txt):
                    print(txt, el.get_attribute('class'))
            except Exception:
                pass
        wait(30)
        browser.close()

if __name__ == '__main__':
    main()
