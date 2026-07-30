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
        # Save HTML of picker before click
        with open(SAVE_DIR/'picker_before.html','w',encoding='utf-8') as f:
            f.write(page.content())
        # Find element with text 北京市 and print tag/class
        el_info = page.evaluate("""() => {
            for (const el of document.querySelectorAll('*')) if (el.textContent.trim()==='北京市') {
                return {tag: el.tagName, cls: el.className, outer: el.outerHTML.slice(0,300)};
            }
            return null;
        }""")
        print('el_info', json.dumps(el_info, ensure_ascii=False, indent=2))
        # Click the specific element via JS using target matching tag/class
        if el_info:
            tag = el_info['tag']
            cls = el_info['cls']
            page.evaluate(f"""() => {{
                const els = document.querySelectorAll('{tag.toLowerCase()}.{cls.replace(/ /g,'.') if cls else ''}');
                for (const el of els) if (el.textContent.trim()==='北京市'){{ el.click(); return true; }}
                return false;
            }}""")
        wait(2)
        # text after
        info2 = page.evaluate("""() => {
            const container = document.querySelector('.uni-picker-container') || document.querySelector('.uni-picker-custom') || document.body;
            const text = Array.from(container.querySelectorAll('*')).map(e => e.textContent.trim()).filter(t => t && t.length < 25);
            return [...new Set(text)].slice(0,120);
        }""")
        print('after click specific:', info2[:60])
        with open(SAVE_DIR/'picker_after.html','w',encoding='utf-8') as f:
            f.write(page.content())
        wait(10)
        browser.close()

if __name__ == '__main__':
    main()
