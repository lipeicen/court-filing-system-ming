import os, sys, time, json
sys.path.insert(0, 'src')
from pathlib import Path
from playwright.sync_api import sync_playwright
from dotenv import load_dotenv
from utils.captcha_solver import CaptchaSolver
load_dotenv()
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
        wait(3); click_text(page, "律师用户"); wait(0.5); click_text(page, "密码登录"); wait(0.5)
        try: page.wait_for_selector("input[type='password']", timeout=5000)
        except Exception: click_text(page, "密码登录"); wait(1)
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
        if "在线立案" in page.content() and "密码登录" not in page.content(): print('login ok'); return True
    return False
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"])
    ctx = browser.new_context(viewport={"width": 1600, "height": 900})
    page = ctx.new_page()
    if not login(page, os.getenv("BEIJING_COURT_USERNAME"), os.getenv("BEIJING_COURT_PASSWORD")):
        print('login failed'); browser.close(); sys.exit(1)
    click_text(page, "在线立案"); wait(3)
    click_text(page, "我要立案"); wait(3)
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
    wait(5)
    # Inspect xzfy component
    info = popup.evaluate("""() => {
        function walk(v) {
            if (!v) return null;
            const tag = v.$options && (v.$options.name || v.$options._componentTag || v.$options.__name);
            if (tag === 'xzfy') return v;
            for (const c of v.$children || []) { const r = walk(c); if (r) return r; }
            return null;
        }
        const x = walk(document.querySelector('uni-app').__vue__);
        const keys = Object.keys(x).filter(k=> typeof x[k] === 'function' || ['fyId','fymc','value','citymc','currentIndex','ajlxList','fyList'].includes(k));
        const obj = {};
        for (const k of keys) {
            try {
                const v = x[k];
                if (typeof v === 'function') obj[k] = 'function';
                else if (Array.isArray(v)) obj[k] = v.length;
                else obj[k] = v;
            } catch (e) { obj[k] = 'err'; }
        }
        obj.watchers = Object.keys(x._watchers || {});
        return obj;
    }""")
    print('info keys', json.dumps(info, ensure_ascii=False, indent=2))
    # dump methods source lengths for changeFy, maybe name variations
    info2 = popup.evaluate("""() => {
        function walk(v) {
            if (!v) return null;
            const tag = v.$options && (v.$options.name || v.$options._componentTag || v.$options.__name);
            if (tag === 'xzfy') return v;
            for (const c of v.$children || []) { const r = walk(c); if (r) return r; }
            return null;
        }
        const x = walk(document.querySelector('uni-app').__vue__);
        const fns = ['changeFy','radioChange','checkboxChange','onClickItem','selectCourt','setCourt','confirm','getFyList','getCityList','getListData'];
        const out = {};
        for (const n of fns) {
            try {
                const f = x[n];
                out[n] = f ? f.toString().slice(0, 300) : 'missing';
            } catch (e) { out[n] = 'err'; }
        }
        return out;
    }""")
    print('methods', json.dumps(info2, ensure_ascii=False, indent=2))
    browser.close()
