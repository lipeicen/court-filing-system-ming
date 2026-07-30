
import os, sys, time, json
sys.path.insert(0, 'src')
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright
from adapters.beijing_court import BeijingCourtAdapter
load_dotenv()

with sync_playwright() as p:
    adapter = BeijingCourtAdapter()
    browser = p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"])
    ctx = browser.new_context(viewport={"width": 1600, "height": 900})
    page = ctx.new_page()
    ok = adapter.login(page, {"username": os.getenv("BEIJING_COURT_USERNAME"), "password": os.getenv("BEIJING_COURT_PASSWORD")})
    if not ok: print('login failed'); browser.close(); sys.exit(1)
    popup = adapter.navigate_to_filing(page)
    adapter.fill_case_form(popup, {"court_name": "北京市海淀区人民法院"})
    # 案由页 dump
    popup.wait_for_selector("text=选择立案案由", timeout=10000)
    time.sleep(2)
    # all visible text nodes
    texts = popup.evaluate("""() => {
        const out = [];
        for (const el of document.querySelectorAll('*')) {
            const txt = el.textContent && el.textContent.trim();
            if (txt && txt.length > 1 && txt.length < 100) out.push({tag: el.tagName, class: el.className, text: txt});
        }
        return out;
    }""")
    # component tree
    tree = popup.evaluate("""() => {
        function walk(v, depth=0) {
            if (!v || depth > 10) return null;
            const tag = v.$options && (v.$options.name || v.$options._componentTag || v.$options.__name || v.$options.__file);
            const keys = Object.keys(v).filter(k=>!k.startsWith('_') && !k.startsWith('$') && k.length < 30).slice(0,8);
            return {tag, keys, children: (v.$children||[]).map(c=>walk(c, depth+1)).filter(Boolean)};
        }
        return walk(document.querySelector('uni-app').__vue__);
    }""")
    print('--- visible texts (first 80) ---')
    for t in texts[:80]: print(t)
    print('\n--- component tree ---')
    print(json.dumps(tree, ensure_ascii=False, indent=2)[:6000])
    popup.screenshot(path='screenshots/probe/case_cause_probe.png')
    browser.close()
