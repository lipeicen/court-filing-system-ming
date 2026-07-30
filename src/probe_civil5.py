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

def save_state(page, name):
    try:
        with open(SAVE_DIR / f"{name}.html", 'w', encoding='utf-8') as f: f.write(page.content())
    except Exception as e: print('html err', e)
    try:
        page.screenshot(path=str(SAVE_DIR / f"{name}.png"), full_page=True)
    except Exception as e: print('png err', e)
    print(f"saved {name}")

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
            print('popup url', popup.url)
            popup.wait_for_selector("text=选择受理法院", timeout=30000)
            save_state(popup, "p5_step1_initial")
            # Try click city 杭州市
            click_text(popup, "杭州市")
            wait(2)
            save_state(popup, "p5_step1_hangzhou")
            # Try click first court card (not 高级/最高)
            cards = popup.query_selector_all(".fd-wsla-checkbox .checklist-box")
            print('court cards', len(cards))
            for i, card in enumerate(cards):
                txt = card.inner_text()
                print('card', i, txt)
            if cards:
                for card in cards:
                    txt = card.inner_text()
                    if '高级' not in txt and '最高' not in txt and '海事' not in txt:
                        card.click()
                        print('clicked court', txt)
                        break
                wait(1)
                save_state(popup, "p5_step1_court_selected")
            # Click applicant type
            click_text(popup, "本人申请")
            wait(1)
            save_state(popup, "p5_step1_applicant")
            # Click next button by text
            click_text(popup, "下一步")
            wait(3)
            save_state(popup, "p5_step2_after_next")
            print('after next url', popup.url)
        browser.close()

if __name__ == '__main__':
    main()
