
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
def get_xzfy(popup):
    return popup.evaluate("""() => {
        function walk(v) {
            if (!v) return null;
            const tag = v.$options && (v.$options.name || v.$options._componentTag || v.$options.__name);
            if (tag === 'xzfy') return v;
            for (const c of v.$children || []) { const r = walk(c); if (r) return r; }
            return null;
        }
        return walk(document.querySelector('uni-app').__vue__);
    }""")
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
    def read_state():
        return popup.evaluate("""() => {
            function walk(v) { if(!v)return null; const tag=v.$options&&(v.$options.name||v.$options._componentTag||v.$options.__name); if(tag==='xzfy') return v; for(const c of v.$children||[]){ const r=walk(c); if(r)return r;} return null;}
            const x=walk(document.querySelector('uni-app').__vue__);
            return {fyId:x.fyId, fymc:x.fymc, ajlxList:(x.ajlxList||[]).length, value:x.value, currentIndex:x.currentIndex};
        }""")
    def try_call(name, args=None):
        try:
            r = popup.evaluate(f"""(args) => {{
                function walk(v) {{ if(!v)return null; const tag=v.$options&&(v.$options.name||v.$options._componentTag||v.$options.__name); if(tag==='xzfy') return v; for(const c of v.$children||[]){{ const r=walk(c); if(r)return r;}} return null;}}
                const x=walk(document.querySelector('uni-app').__vue__);
                const f=x[{json.dumps(name)}];
                if(!f) return 'missing';
                const a = args || [];
                const res = f.apply(x, a);
                return {{ok:true, res:res}};
            }}""", args)
            return r
        except Exception as e:
            return {'err': str(e)}
    print('initial state', read_state())
    # candidate 1: set directly + forceUpdate
    print('candidate1: set fyId + fymc')
    popup.evaluate("""() => {
        function walk(v) { if(!v)return null; const tag=v.$options&&(v.$options.name||v.$options._componentTag||v.$options.__name); if(tag==='xzfy') return v; for(const c of v.$children||[]){ const r=walk(c); if(r)return r;} return null;}
        const x=walk(document.querySelector('uni-app').__vue__);
        x.fyId='6'; x.fymc='北京市海淀区人民法院'; x.$forceUpdate();
    }""")
    wait(2); print('after set', read_state())
    # candidate 2: checkboxChange
    print('candidate2: checkboxChange', try_call('checkboxChange', [{'detail':{'value':'6'}}]))
    wait(2); print('after checkboxChange', read_state())
    # candidate 3: change
    print('candidate3: change', try_call('change', [{'detail':{'value':'6'}}]))
    wait(2); print('after change', read_state())
    # candidate 4: bindChange
    print('candidate4: bindChange', try_call('bindChange', [{'detail':{'value':'6'}}]))
    wait(2); print('after bindChange', read_state())
    # candidate 5: changeFy
    print('candidate5: changeFy', try_call('changeFy'))
    wait(2); print('after changeFy', read_state())
    # candidate 6: onClickItem
    print('candidate6: onClickItem', try_call('onClickItem', ['6']))
    wait(2); print('after onClickItem', read_state())
    # candidate 7: simulate native click on label and input using Playwright
    print('playwright click on text=北京市海淀区人民法院')
    try:
        popup.locator("text=北京市海淀区人民法院").first.click(timeout=3000)
    except Exception as e: print('click err', e)
    wait(2); print('after click text', read_state())
    # try clicking the radio/checkbox icon preceding it
    print('playwright click on label containing text')
    try:
        el = popup.locator("uni-label:has-text('北京市海淀区人民法院')").first
        el.click(timeout=3000)
    except Exception as e: print('label click err', e)
    wait(2); print('after label click', read_state())
    # screenshot
    popup.screenshot(path=str(SAVE_DIR/'xzfy_end.png'))
    browser.close()
