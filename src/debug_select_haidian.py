#!/usr/bin/env python3
import os, sys, time, json
sys.path.insert(0, os.path.dirname(__file__))
from pathlib import Path
from playwright.sync_api import sync_playwright
from dotenv import load_dotenv
from utils.captcha_solver import CaptchaSolver
load_dotenv()

HEADLESS = False
SLOW_MO = 300
SAVE_DIR = Path("screenshots/probe")
SAVE_DIR.mkdir(parents=True, exist_ok=True)

def wait(t=1.0): time.sleep(t)

def click_text(page, text, timeout=5000):
    for fn in [lambda: page.get_by_text(text, exact=True).click(timeout=timeout),
               lambda: page.click(f"text={text}", timeout=timeout),
               lambda: page.evaluate("""(t) => { for (const el of document.querySelectorAll('*')) if (el.textContent && el.textContent.trim()===t){ el.click(); return true; } return false; }""", text)]:
        try: fn(); wait(0.5); return True
        except Exception: pass
    return False

def login(page, u, p, max_retry=3):
    for attempt in range(1, max_retry+1):
        page.goto("https://zxfw.court.gov.cn/zxfw/#/pagesGrxx/pc/login/index", wait_until="domcontentloaded")
        wait(3)
        click_text(page, "律师用户")
        wait(0.5)
        click_text(page, "密码登录")
        wait(0.5)
        try: page.wait_for_selector("input[type='password']", timeout=5000)
        except Exception:
            click_text(page, "密码登录")
            wait(1)
        inputs = page.query_selector_all(".uni-input-input")
        if len(inputs) >= 2: inputs[0].fill(u); inputs[1].fill(p)
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
    return False

with sync_playwright() as p:
    browser = p.chromium.launch(headless=HEADLESS, slow_mo=SLOW_MO, args=["--disable-blink-features=AutomationControlled"])
    ctx = browser.new_context(viewport={"width": 1600, "height": 900})
    page = ctx.new_page()
    if not login(page, os.getenv("BEIJING_COURT_USERNAME"), os.getenv("BEIJING_COURT_PASSWORD")):
        print('login failed'); browser.close(); sys.exit(1)
    click_text(page, "在线立案")
    wait(3)
    click_text(page, "我要立案")
    wait(3)
    # set storage only, no header update
    page.evaluate("""() => { uni.setStorageSync('provinceId', '110000'); return 'storage'; }""")
    wait(2)
    item_info = page.evaluate("""() => {
        const items = document.querySelectorAll('.fd-children-item');
        let el = null;
        for (const item of items) if (item.textContent.includes('民事一审')) { el = item; break; }
        if (!el) return {err: 'no element'};
        let v = el.__vue__;
        while (v) {
            if (v.$options && (v.$options.name || v.$options._componentTag) === 'pagesWsla-pc-zxla-pick-case-type-index') {
                const list = v.typeDataList || [];
                for (const type of list) if (type.children) for (const child of type.children) if (child.name === '民事一审') return {item: child};
            }
            v = v.$parent;
        }
        return {err: 'not found'};
    }""")
    item_json = json.dumps(item_info['item'], ensure_ascii=False)
    page.evaluate(f"""() => {{
        const target = {item_json};
        const items = document.querySelectorAll('.fd-children-item');
        let el = null;
        for (const item of items) if (item.textContent.includes('民事一审')) {{ el = item; break; }}
        let v = el.__vue__;
        while (v) {{
            if (v.$options && (v.$options.name || v.$options._componentTag) === 'pagesWsla-pc-zxla-pick-case-type-index') {{ v.toZxla(target); return 'called'; }}
            v = v.$parent;
        }}
    }}""")
    popup = ctx.wait_for_event('page', timeout=30000)
    popup.wait_for_selector("text=选择受理法院", timeout=30000)
    print('popup ready', popup.url)
    wait(5)
    # get xzfy data
    x = popup.evaluate("""() => {
        function walk(v) {
            if (!v) return null;
            const tag = v.$options && (v.$options.name || v.$options._componentTag || v.$options.__name);
            if (tag === 'xzfy') return v;
            for (const c of v.$children || []) { const r = walk(c); if (r) return r; }
            return null;
        }
        const x = walk(document.querySelector('uni-app').__vue__);
        return {value: x.value, citymc: x.citymc, fyId: x.fyId, fymc: x.fymc, fyList: x.fyList.map(f=>({value:f.value, text:f.text}))};
    }""")
    print('xzfy state', json.dumps({k:v for k,v in x.items() if k!='fyList'}, ensure_ascii=False))
    with open(SAVE_DIR / 'haidian_fylist.json', 'w', encoding='utf-8') as f:
        json.dump(x['fyList'], f, ensure_ascii=False, indent=2)
    for fy in x['fyList']:
        print(fy['value'], fy['text'])
    popup.screenshot(path=str(SAVE_DIR / 'haidian_01_ready.png'), full_page=True)

    # select haidian via JS
    haidian = [fy['value'] for fy in x['fyList'] if fy['text'] == '北京市海淀区人民法院'][0]
    print('haidian value', haidian)
    popup.evaluate(f"""() => {{
        function walk(v) {{
            if (!v) return null;
            const tag = v.$options && (v.$options.name || v.$options._componentTag || v.$options.__name);
            if (tag === 'xzfy') return v;
            for (const c of v.$children || []) {{ const r = walk(c); if (r) return r; }}
            return null;
        }}
        const x = walk(document.querySelector('uni-app').__vue__);
        x.fyId = '{haidian}';
        x.fymc = '北京市海淀区人民法院';
        if (typeof x.changeFy === 'function') x.changeFy();
        x.$forceUpdate && x.$forceUpdate();
        return 'set';
    }}""")
    wait(3)
    x2 = popup.evaluate("""() => {
        function walk(v) {
            if (!v) return null;
            const tag = v.$options && (v.$options.name || v.$options._componentTag || v.$options.__name);
            if (tag === 'xzfy') return v;
            for (const c of v.$children || []) { const r = walk(c); if (r) return r; }
            return null;
        }
        const x = walk(document.querySelector('uni-app').__vue__);
        return {fyId: x.fyId, fymc: x.fymc};
    }""")
    print('after js', x2)
    popup.screenshot(path=str(SAVE_DIR / 'haidian_02_selected.png'), full_page=True)
    with open(SAVE_DIR / 'haidian_02_selected.html', 'w', encoding='utf-8') as f: f.write(popup.content())

    # click 本人申请
    click_text(popup, "本人申请")
    wait(1)
    popup.screenshot(path=str(SAVE_DIR / 'haidian_03_agree.png'), full_page=True)

    # click next
    try: popup.get_by_role('button', name='下一步').click(timeout=5000)
    except Exception: popup.click("text=下一步", timeout=5000)
    wait(3)
    popup.screenshot(path=str(SAVE_DIR / 'haidian_04_next.png'), full_page=True)
    with open(SAVE_DIR / 'haidian_04_next.html', 'w', encoding='utf-8') as f: f.write(popup.content())
    print('done', popup.url)
    wait(8)
    browser.close()
