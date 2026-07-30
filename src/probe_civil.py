#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""调用 toZxla 并传入正确的民事一审 item。"""
import os, sys, time, json
sys.path.insert(0, os.path.dirname(__file__))
from pathlib import Path
from playwright.sync_api import sync_playwright
from dotenv import load_dotenv
load_dotenv()

HEADLESS = True
SAVE_DIR = Path("screenshots/probe")
SAVE_DIR.mkdir(parents=True, exist_ok=True)

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
    html_path = SAVE_DIR / f"{name}.html"
    png_path = SAVE_DIR / f"{name}.png"
    try:
        with open(html_path, 'w', encoding='utf-8') as f: f.write(page.content())
    except Exception as e: print('save html err', e)
    try:
        page.screenshot(path=str(png_path), full_page=True)
    except Exception as e: print('save png err', e)
    print(f"saved {name}")

def login(page, username, password, max_retry=3):
    for attempt in range(1, max_retry+1):
        print(f'login attempt {attempt}')
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
                from utils.captcha_solver import CaptchaSolver
                with open(SAVE_DIR / "captcha.png", 'rb') as f: b = f.read()
                code = CaptchaSolver().solve_image_captcha(b)
                inputs[2].fill(code)
        for sel in [".fd-login-btn", "button:has-text('登录')", ".login-btn"]:
            try: page.click(sel, timeout=3000); break
            except Exception: pass
        wait(5)
        content = page.content()
        if "在线立案" in content and "密码登录" not in content:
            print('login ok')
            return True
        print('login failed, url', page.url)
    return False

def main():
    username = os.getenv("BEIJING_COURT_USERNAME")
    password = os.getenv("BEIJING_COURT_PASSWORD")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS, args=["--disable-blink-features=AutomationControlled"])
        ctx = browser.new_context(viewport={"width": 1600, "height": 900})
        page = ctx.new_page()
        page.on("console", lambda msg: print("console:", msg.type, msg.text))
        page.on("pageerror", lambda err: print("pageerror:", err))
        if not login(page, username, password):
            print("LOGIN FAILED"); browser.close(); return
        print("LOGIN OK", page.url)
        click_text(page, "在线立案")
        wait(5)
        save_state(page, "online_filing")

        # 获取 typeDataList 和民事一审 item
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
                                if (child.name === '民事一审') {
                                    return {item: child, typeName: type.name, allKeys: Object.keys(child)};
                                }
                            }
                        }
                    }
                    return {err: 'not found in typeDataList', listLen: list.length, firstType: list.length > 0 ? list[0].name : null};
                }
                v = v.$parent;
            }
            return {err: 'page comp not found'};
        }""")
        print('item_info', json.dumps(item_info, ensure_ascii=False, indent=2))

        # 调用 toZxla(item)
        if item_info and item_info.get('item'):
            item_json = json.dumps(item_info['item'], ensure_ascii=False)
            try:
                res = page.evaluate(f"""() => {{
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
                print('toZxla res', res)
                # 等待路由跳转，最多30秒
                for i in range(6):
                    wait(5)
                    print(f'wait {i+1} url', page.url)
                    if '/pagesWsla/pc/zxla/pick-case-type/index' not in page.url:
                        break
                save_state(page, "after_tozxla_with_item")
            except Exception as e:
                print('toZxla err', e)
        # 查看路由跳转方法源码
        try:
            source = page.evaluate("""() => {
                const items = document.querySelectorAll('.fd-children-item');
                let el = null;
                for (const item of items) if (item.textContent.includes('民事一审')) { el = item; break; }
                let v = el.__vue__;
                while (v) {
                    if (v.$options && (v.$options.name || v.$options._componentTag) === 'pagesWsla-pc-zxla-pick-case-type-index') {
                        return v.$options.methods.toZxla.toString();
                    }
                    v = v.$parent;
                }
                return null;
            }""")
            print('toZxla source', source[:2000])
        except Exception as e: print('source err', e)

        print('done')
        browser.close()

if __name__ == '__main__':
    main()
