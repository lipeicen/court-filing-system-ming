from loguru import logger
from .base import CourtAdapter
from utils.captcha_solver import CaptchaSolver
import os, time, json, re
from pathlib import Path
from playwright.sync_api import Page, BrowserContext


class BeijingCourtAdapter(CourtAdapter):
    """人民法院在线服务网(北京)民事一审自动立案适配器"""

    PROVINCE_ID = "110000"

    @property
    def court_name(self) -> str:
        return "人民法院在线服务"

    @property
    def court_code(self) -> str:
        return "beijing"

    @property
    def base_url(self) -> str:
        return "https://zxfw.court.gov.cn"

    def __init__(self):
        self.save_dir = Path("screenshots/probe")
        self.save_dir.mkdir(parents=True, exist_ok=True)
        self.popup = None
        self.main_page = None

    def _wait(self, t=1.0):
        time.sleep(t)

    def _save_state(self, page: Page, name: str):
        try:
            html_path = self.save_dir / f"{name}.html"
            png_path = self.save_dir / f"{name}.png"
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(page.content())
            try:
                page.screenshot(path=str(png_path), timeout=5000)
            except Exception as e2:
                logger.warning(f"screenshot {name} skipped: {e2}")
            logger.info(f"saved state {name}")
        except Exception as e:
            logger.error(f"save state {name} failed: {e}")

    def _click_text(self, page: Page, text: str, timeout=5000, exact=False) -> bool:
        """优先使用 Playwright 文本选择器点击，失败再回退到 JS"""
        for fn in [
            lambda: page.get_by_text(text, exact=exact).click(timeout=timeout),
            lambda: page.click(f"text={text}", timeout=timeout),
            lambda: page.evaluate(
                """(text) => {
                    const all = document.querySelectorAll('*');
                    for (const el of all) if (el.textContent && el.textContent.trim() === text) { el.click(); return true; }
                    return false;
                }""", text
            ),
        ]:
            try:
                fn()
                self._wait(0.5)
                return True
            except Exception:
                pass
        return False

    def _find_page_vue(self, page: Page, tag_name: str):
        """在页面 Vue 组件树中查找指定名称的组件实例"""
        return page.evaluate(
            """(tagName) => {
                const app = document.querySelector('uni-app');
                if (!app) return {err: 'no uni-app'};
                const root = app.__vue__;
                function find(v) {
                    if (!v) return null;
                    const tag = v.$options && (v.$options.name || v.$options._componentTag || v.$options.__name);
                    if (tag === tagName) return v;
                    for (const c of v.$children || []) { const r = find(c); if (r) return r; }
                    return null;
                }
                const comp = find(root);
                return comp ? {found: true} : {err: 'not found'};
            }""", tag_name
        )

    def _set_province_beijing(self, page: Page):
        """在案件类型选择页把省份切到北京：直接操作 commonHeader 与 Vue 状态"""
        logger.info("设置省份为北京")
        page.evaluate(
            """(provinceId) => {
                const app = document.querySelector('uni-app').__vue__;
                function find(v, tagName) {
                    if (!v) return null;
                    const tag = v.$options && (v.$options.name || v.$options._componentTag || v.$options.__name);
                    if (tag === tagName) return v;
                    for (const c of v.$children || []) { const r = find(c, tagName); if (r) return r; }
                    return null;
                }
                // 1) 更新头部组件省份索引
                const header = find(app, 'commonHeader');
                if (header) {
                    const idx = (header.provinces || []).indexOf(provinceId);
                    header.currentAreaIndex = idx > 0 ? idx : 1;
                    if (typeof header.updateHeaderStorage === 'function') header.updateHeaderStorage();
                }
                // 2) 同步案件类型页(如果有)
                const pick = find(app, 'pagesWsla-pc-zxla-pick-case-type-index');
                if (pick && typeof pick.getListData === 'function') {
                    try { pick.getListData(); } catch (e) {}
                }
                uni.setStorageSync('provinceId', provinceId);
                return 'done';
            }""", self.PROVINCE_ID
        )
        self._wait(2.5)

    def login(self, page: Page, credentials: dict, max_retry: int = 3) -> bool:
        self.main_page = page
        username = credentials.get("username", "")
        password = credentials.get("password", "")
        for attempt in range(1, max_retry + 1):
            logger.info(f"login attempt {attempt}")
            page.goto(f"{self.base_url}/zxfw/#/pagesGrxx/pc/login/index", wait_until="domcontentloaded")
            self._wait(3)
            self._click_text(page, "律师用户", timeout=3000)
            self._wait(0.5)
            self._click_text(page, "密码登录", timeout=3000)
            self._wait(1)
            try:
                page.wait_for_selector("input[type='password']", timeout=5000)
            except Exception:
                self._click_text(page, "密码登录", timeout=3000)
                self._wait(1)

            inputs = page.query_selector_all(".uni-input-input")
            if len(inputs) >= 2:
                inputs[0].fill(username)
                inputs[1].fill(password)
            if len(inputs) >= 3:
                try:
                    # find captcha image (class fd-images-code or inside fd-captcha)
                    captcha_img = None
                    candidates = page.query_selector_all("img")
                    for img in candidates:
                        cls = img.evaluate("el => el.className") or ""
                        if "fd-images-code" in cls or "captcha" in cls:
                            captcha_img = img
                            break
                    if not captcha_img:
                        # fallback to first image in .fd-captcha
                        captcha_img = page.locator(".fd-captcha img, .fd-images-code").first
                    if captcha_img:
                        # capture data URL or screenshot
                        data_url = captcha_img.evaluate("""el => {
                            if (el.src && el.src.startsWith('data:')) return el.src;
                            return null;
                        }""")
                        if data_url:
                            import base64
                            header, b64 = data_url.split(',', 1)
                            image_bytes = base64.b64decode(b64)
                        else:
                            image_bytes = captcha_img.screenshot()
                        code = CaptchaSolver().solve_image_captcha(image_bytes)
                        inputs[2].fill(code)
                except Exception as e:
                    logger.warning(f"captcha handling skipped: {e}")
            try:
                page.click(".fd-login-btn", timeout=5000)
            except Exception:
                try:
                    page.click("text=登录", timeout=5000)
                except Exception as e:
                    logger.warning(f"click login failed: {e}")
            self._wait(5)
            content = page.content()
            if "在线立案" in content and "密码登录" not in content:
                logger.info("login ok")
                self._save_state(page, "login_success")
                return True
            logger.warning(f"login failed, url {page.url}")
            self._save_state(page, f"login_failed_{attempt}")
        return False

    def navigate_to_filing(self, page: Page) -> Page:
        """导航到民事一审立案表单页面，返回新打开的页面实例"""
        logger.info("导航到民事一审立案页面")
        self._click_text(page, "在线立案")
        self._wait(3)
        self._click_text(page, "我要立案")
        self._wait(3)
        self._save_state(page, "pick_case_type")

        self._set_province_beijing(page)
        self._save_state(page, "pick_case_type_after_beijing")

        # 点击“民事一审”会在新窗口打开 wsla/index
        if not self._click_text(page, "民事一审", timeout=10000, exact=True):
            raise Exception("无法点击民事一审")

        # 等待新页面打开
        new_page = None
        try:
            new_page = page.context.wait_for_event("page", timeout=15000)
            logger.info(f"new page opened: {new_page.url}")
        except Exception as e:
            logger.warning(f"wait_for_event page timeout: {e}")
            for _ in range(15):
                self._wait(1)
                for pg in page.context.pages:
                    if "wsla/index" in pg.url:
                        new_page = pg
                        break
                if new_page and not new_page.is_closed():
                    break

        if not new_page:
            raise Exception("民事一审窗口未打开")

        # 等待页面加载到选择受理法院
        try:
            new_page.wait_for_selector("text=选择受理法院", timeout=30000)
        except Exception as e:
            logger.warning(f"等待选择受理法院超时: {e}")

        self.popup = new_page
        self._save_state(new_page, "civil_first")
        return new_page

    def fill_case_form(self, page: Page, case_data: dict) -> None:
        logger.info("开始填写案件信息...")
        self._select_court(page, case_data)
        self._agree_notice(page)
        self._select_case_cause(page, case_data)
        self._save_state(page, "form_filling")

    def _find_vue_component(self, page: Page, tag_name: str):
        """在页面 Vue 树中查找组件实例"""
        return page.evaluate(
            """(tagName) => {
                const app = document.querySelector('uni-app');
                if (!app || !app.__vue__) return {err: 'no vue'};
                function find(v) {
                    if (!v) return null;
                    const tag = v.$options && (v.$options.name || v.$options._componentTag || v.$options.__name);
                    if (tag === tagName) return v;
                    for (const c of v.$children || []) { const r = find(c); if (r) return r; }
                    return null;
                }
                const comp = find(app.__vue__);
                return comp ? {found: true} : {err: 'not found'};
            }""", tag_name
        )

    def _set_xzfy_beijing(self, page: Page):
        """在 wsla/index 选择受理法院页，把 xzfy 组件切到北京"""
        logger.info("切换受理法院页省份为北京")
        page.evaluate(
            """(provinceId) => {
                function find(v, tagName) {
                    if (!v) return null;
                    const tag = v.$options && (v.$options.name || v.$options._componentTag || v.$options.__name);
                    if (tag === tagName) return v;
                    for (const c of v.$children || []) { const r = find(c, tagName); if (r) return r; }
                    return null;
                }
                const app = document.querySelector('uni-app').__vue__;
                // 1) 持久化省份，后续接口都依赖
                uni.setStorageSync('provinceId', provinceId);
                // 2) 同步 commonHeader 省份索引
                const header = find(app, 'commonHeader');
                if (header) {
                    const idx = (header.provinces || []).indexOf(provinceId);
                    header.currentAreaIndex = idx > 0 ? idx : 1;
                }
                // 3) 触发 xzfy 城市列表刷新
                const x = find(app, 'xzfy');
                if (!x) return {err: 'no xzfy'};
                x.value = provinceId;
                x.citymc = '北京市';
                x.fyId = '';
                x.fymc = '';
                x.currentIndex = 0;
                x.chooseValue = 0;
                x.fyList = [];
                if (typeof x.getCityList === 'function') x.getCityList();
                x.$forceUpdate();
                return 'ok';
            }""", self.PROVINCE_ID
        )
        self._wait(4)

    def _click_court_card(self, page: Page, court_name: str) -> bool:
        """通过操作 Vue 状态选择法院(uni-app 渲染的 radio label 点击不触发响应)"""
        if not court_name:
            return False
        selected = page.evaluate(
            """(name) => {
                function find(v, tagName) {
                    if (!v) return null;
                    const tag = v.$options && (v.$options.name || v.$options._componentTag || v.$options.__name);
                    if (tag === tagName) return v;
                    for (const c of v.$children || []) { const r = find(c, tagName); if (r) return r; }
                    return null;
                }
                const app = document.querySelector('uni-app').__vue__;
                const x = find(app, 'xzfy');
                if (!x || !x.fyList) return {err: 'no xzfy or fyList'};
                for (let i = 0; i < x.fyList.length; i++) {
                    const fy = x.fyList[i];
                    if (fy.text && fy.text.includes(name)) {
                        x.fyId = String(fy.value);
                        x.fymc = fy.text;
                        x.currentIndex = String(fy.value);
                        x.chooseValue = fy.value;
                        x.$forceUpdate();
                        return {ok: true, court: fy.text, value: fy.value};
                    }
                }
                return {err: 'court not found in fyList', name: name};
            }""", court_name
        )
        self._wait(0.5)
        if selected.get('ok'):
            logger.info(f"selected court by state: {selected.get('court')}")
            return True
        logger.warning(f"select court failed: {selected}")
        return False

    def _select_court(self, page: Page, case_data: dict):
        logger.info("选择受理法院...")
        try:
            page.wait_for_selector("text=选择受理法院", timeout=30000)
        except Exception:
            pass
        self._save_state(page, "court_select")

        # 关键：先切换到北京省份，并清空旧选择
        self._set_xzfy_beijing(page)
        self._save_state(page, "court_select_beijing")

        target_court = case_data.get("court_name", "")
        if target_court:
            if not self._click_court_card(page, target_court):
                logger.warning(f"未选择到指定法院: {target_court}")
        else:
            # 默认选择第一个基层法院(排除中级/高级/最高/海事/知识产权/金融/互联网/铁路)
            selected = page.evaluate(
                """() => {
                    function findXzfy(v) {
                        if (!v) return null;
                        const tag = v.$options && (v.$options.name || v.$options._componentTag || v.$options.__name);
                        if (tag === 'xzfy') return v;
                        for (const c of v.$children || []) { const r = findXzfy(c); if (r) return r; }
                        return null;
                    }
                    const x = findXzfy(document.querySelector('uni-app').__vue__);
                    if (x && x.fyList) {
                        for (const fy of x.fyList) {
                            const txt = fy.text || '';
                            if (/高级|最高|中级|海事|知识产权|金融|互联网|铁路/.test(txt)) continue;
                            if (txt.includes('人民法院')) {
                                x.fyId = String(fy.value);
                                x.fymc = txt;
                                x.currentIndex = String(fy.value);
                                x.chooseValue = fy.value;
                                x.$forceUpdate();
                                return txt;
                            }
                        }
                    }
                    return null;
                }"""
            )
            logger.info(f"auto selected court: {selected}")
            self._wait(0.5)

        self._save_state(page, "after_court_selected")

        # 选择“本人申请”
        self._click_text(page, "本人申请", timeout=5000)
        self._wait(0.5)

        # 关闭可能弹出的提示层(综治中心等)
        for btn_text in ["关闭", "我知道了", "不再提醒"]:
            self._click_text(page, btn_text, timeout=3000)
        self._wait(0.5)

        # 点击下一步：真实点击失败时直接调用组件 nextStep
        next_clicked = False
        if not self._click_text(page, "下一步", timeout=5000):
            try:
                page.click("uni-button[type='primary']", timeout=3000)
                next_clicked = True
            except Exception as e:
                logger.warning(f"下一步点击失败: {e}")
        else:
            next_clicked = True
        if not next_clicked:
            try:
                page.evaluate(
                    """() => {
                        function find(v, tagName) {
                            if (!v) return null;
                            const tag = v.$options && (v.$options.name || v.$options._componentTag || v.$options.__name);
                            if (tag === tagName) return v;
                            for (const c of v.$children || []) { const r = find(c, tagName); if (r) return r; }
                            return null;
                        }
                        const x = find(document.querySelector('uni-app').__vue__, 'xzfy');
                        if (x && typeof x.nextStep === 'function') { x.nextStep(); return 'nextStep called'; }
                        return 'no nextStep';
                    }"""
                )
            except Exception as e:
                logger.warning(f"nextStep 调用失败: {e}")
        self._wait(3)
        self._save_state(page, "after_court_next")

    def _agree_notice(self, page: Page):
        logger.info("阅读须知...")
        try:
            page.wait_for_selector("text=立案须知", timeout=10000)
        except Exception:
            pass
        try:
            self._save_state(page, "notice")
        except Exception as e:
            logger.warning(f"notice state save skipped: {e}")
        # 勾选“已阅读同意立案须知内容”
        for agree_text in ["已阅读同意立案须知内容", "已阅读同意", "已阅读并同意"]:
            try:
                agree = page.locator(f"text={agree_text}")
                if agree.count():
                    agree.click()
                    self._wait(0.5)
                    break
            except Exception:
                pass
        else:
            try:
                cb = page.locator(".uni-checkbox-input").first
                if cb.count():
                    cb.click()
                    self._wait(0.5)
            except Exception as e:
                logger.warning(f"勾选同意失败: {e}")

        # 点击下一步，并处理连续弹窗
        try:
            page.locator("uni-button").filter(has_text="下一步").click(timeout=5000)
        except Exception:
            self._click_text(page, "下一步", timeout=5000)
        self._wait(2)
        try:
            self._save_state(page, "notice_next")
        except Exception as e:
            logger.warning(f"notice_next state save skipped: {e}")

        # 处理要素式/智能识别弹窗 + 立案方式选择
        for i in range(5):
            handled = False
            # 1) 优先关闭“要素式立案”提示
            for btn in ["不选择要素式立案", "不体验智能识别要素式立案服务"]:
                try:
                    loc = page.locator("uni-button").filter(has_text=btn)
                    if loc.count() and loc.first.is_visible():
                        loc.first.click(timeout=3000)
                        logger.info(f"弹窗按钮: {btn}")
                        handled = True
                        self._wait(2)
                        break
                except Exception:
                    continue
            if handled:
                try:
                    self._save_state(page, f"notice_popup_{i}")
                except Exception as e:
                    logger.warning(f"notice_popup_{i} state save skipped: {e}")
                continue

            # 2) 选择立案方式：默认“未准备诉状”
            if self._has_text(page, "请选择立案方式"):
                try:
                    loc = page.locator("text=未准备诉状").first
                    if loc.is_visible():
                        loc.click(timeout=5000)
                        logger.info("选择立案方式: 未准备诉状")
                        self._wait(2)
                        handled = True
                        try:
                            self._save_state(page, f"notice_popup_{i}")
                        except Exception as e:
                            logger.warning(f"notice_popup_{i} state save skipped: {e}")
                        break
                except Exception as e:
                    logger.warning(f"选择未准备诉状失败: {e}")
                # 兜底选择“已准备诉状”
                try:
                    loc = page.locator("text=已准备诉状").first
                    if loc.is_visible():
                        loc.click(timeout=5000)
                        logger.info("选择立案方式: 已准备诉状")
                        self._wait(2)
                        handled = True
                        try:
                            self._save_state(page, f"notice_popup_{i}")
                        except Exception as e:
                            logger.warning(f"notice_popup_{i} state save skipped: {e}")
                        break
                except Exception as e:
                    logger.warning(f"选择已准备诉状失败: {e}")

            if not handled:
                break

        # 若仍停留在须知页面，再次点击下一步
        if (self._has_text(page, "立案须知") and self._has_text(page, "下一步")
                and not self._has_text(page, "选择立案案由")):
            try:
                page.locator("uni-button").filter(has_text="下一步").click(timeout=5000)
            except Exception:
                self._click_text(page, "下一步", timeout=5000)
            self._wait(2)
        self._save_state(page, "notice_after_popup")

    def _has_text(self, page: Page, text: str) -> bool:
        try:
            return page.locator(f"text={text}").count() > 0
        except Exception:
            return False

    def _get_active_step_text(self, page: Page) -> str:
        """获取顶部进度条当前高亮步骤文本"""
        try:
            active = page.locator('.fd-com-step-item--active, .fd-step-item--active, .step-item--active, .active').first
            if active.count():
                return (active.inner_text() or '').strip()[:20]
        except Exception:
            pass
        return ""

    def _is_on_success_page(self, page: Page) -> bool:
        """判断是否真的到了提交成功页（而不是进度条标签）"""
        content = page.content()
        if "提交成功" not in content:
            return False
        if page.locator("button:has-text('上一步'), uni-button:has-text('上一步')").count() > 0:
            return False
        if page.locator("button:has-text('下一步'), uni-button:has-text('下一步')").count() > 0:
            return False
        if page.locator("button:has-text('返回'), uni-button:has-text('返回'), button:has-text('返回首页'), uni-button:has-text('返回首页'), button:has-text('查看案件'), uni-button:has-text('查看案件')").count() > 0:
            return True
        # 兜底：顶部进度条当前步骤为“提交成功”且无返回按钮时也算成功
        active = self._get_active_step_text(page)
        if active == "提交成功":
            return True
        return False

    def _select_case_cause(self, page: Page, case_data: dict):
        logger.info("选择立案案由/法院...")
        # 1) 处理“选择立案方式”弹层/页面(未准备诉状 / 已准备诉状)
        try:
            page.wait_for_selector("text=请选择立案方式", timeout=10000)
            logger.info("选择立案方式: 未准备诉状")
            page.locator("text=未准备诉状").first.click(timeout=5000)
            self._wait(3)
        except Exception:
            logger.info("未出现选择立案方式页面")

        # 2) 等待案由选择页
        try:
            page.wait_for_selector("text=选择立案案由", timeout=10000)
        except Exception:
            pass
        self._save_state(page, "case_cause")

        # 3) 选择具体法院（单选）
        court_name = case_data.get("court_name") or getattr(self, "court_name", "")
        if court_name:
            try:
                court_label = page.locator('uni-label, label, uni-view, view').filter(has_text=re.compile(re.escape(court_name))).first
                if court_label.count() and court_label.is_visible(timeout=3000):
                    court_label.click(timeout=5000)
                    logger.info(f"选择法院: {court_name}")
                    self._wait(1)
                else:
                    res = page.evaluate("""(courtName) => {
                        const labels = Array.from(document.querySelectorAll('uni-label, label, uni-view, view'));
                        const lbl = labels.find(el => (el.innerText||'').trim().includes(courtName));
                        if (!lbl) return {err: 'label not found'};
                        lbl.click();
                        return {ok: true};
                    }""", court_name)
                    logger.info(f"JS选择法院: {court_name} -> {res}")
            except Exception as e:
                logger.warning(f"选择法院失败: {e}")

        # 4) 申请人类型（默认 本人申请）
        try:
            applicant_type = case_data.get("applicant_type", "本人申请")
            type_label = page.locator('uni-label, label').filter(has_text=re.compile(applicant_type)).first
            if type_label.count() and type_label.is_visible(timeout=2000):
                type_label.click(timeout=3000)
                logger.info(f"选择申请人类型: {applicant_type}")
        except Exception as e:
            logger.debug(f"申请人类型选择忽略: {e}")

        self._wait(1)
        self._save_state(page, "court_selected")

        # 5) 案由搜索（如果存在搜索框）
        cause_keyword = case_data.get("metadata", {}).get("case_cause", "") or "买卖合同纠纷"
        try:
            res = page.evaluate(r"""(args) => {
                const keyword = args.keyword;
                function isVisible(el) { if (!el) return false; const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; }
                const inputs = Array.from(document.querySelectorAll('input.uni-input-input, input[type="text"], uni-input input')).filter(isVisible);
                const inp = inputs.find(i => (i.placeholder || '').includes('搜索') || (i.placeholder || '').includes('关键词') || (i.placeholder || '').includes('案由')) || inputs[0];
                if (!inp) return {err: 'no input'};
                inp.value = keyword;
                inp.dispatchEvent(new Event('input', {bubbles: true}));
                inp.dispatchEvent(new Event('change', {bubbles: true}));
                return {ok: true};
            }""", {"keyword": cause_keyword})
            logger.info(f"案由搜索输入: {cause_keyword} -> {res}")
            self._wait(1)
            search_btn = page.locator('uni-button, button').filter(has_text=re.compile('搜索')).first
            if search_btn.count() and search_btn.is_visible(timeout=2000):
                search_btn.click(timeout=5000)
                logger.info("点击案由搜索")
                self._wait(3)
            # 选择第一个匹配结果
            opts = page.locator('uni-view, view, uni-text, text').filter(has_text=re.compile(re.escape(cause_keyword))).all()
            if opts:
                opts[0].click(timeout=5000)
                logger.info(f"选择案由结果: {cause_keyword}")
            else:
                first_opt = page.locator('.uni-data-tree-item, .uni-picker-item, .uni-list-item, uni-view, view').first
                if first_opt.count() and first_opt.is_visible(timeout=2000):
                    first_opt.click(timeout=3000)
                    logger.info("选择第一个案由结果")
            self._wait(2)
        except Exception as e:
            logger.warning(f"案由搜索失败: {e}")

        self._save_state(page, "case_cause_selected")

        # 6) 下一步（进入上传诉讼材料页面）
        self._click_page_bottom_next(page)
        self._wait(5)
        self._save_state(page, "case_cause_next")


    def probe_form_structure(self, page: Page, name: str = "form_probe"):
        """保存表单页面结构供分析"""
        try:
            html_path = self.save_dir / f"{name}.html"
            png_path = self.save_dir / f"{name}.png"
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(page.content())
            page.screenshot(path=str(png_path), full_page=True)
            logger.info(f"form probe saved: {name}")
        except Exception as e:
            logger.error(f"form probe failed: {e}")

    def upload_documents(self, page: Page, documents: list) -> None:
        logger.info("上传案件材料...")
        try:
            page.wait_for_selector("text=上传诉讼材料", timeout=10000)
        except Exception:
            pass
        self._save_state(page, "upload_before")

        # Map documents to buckets by category keywords (documents come from CaseDocument.to_dict -> 'type')
        category_map = {
            '起诉状': ['起诉状', '起诉材料'],
            '身份证明': ['身份证明', '当事人身份证明'],
            '证据': ['证据', '证据目录'],
            '委托书': ['委托', '代理人', '授权'],
            '送达地址确认书': ['送达'],
            '其他材料': ['其他'],
        }
        buckets = {}
        for doc in documents:
            doc_path = doc.get('path') if isinstance(doc, dict) else doc.path
            dtype = (doc.get('type') if isinstance(doc, dict) else getattr(doc, 'doc_type', '')) or ''
            matched = False
            for cat, kws in category_map.items():
                if any(k in dtype for k in kws):
                    buckets.setdefault(cat, []).append(doc_path)
                    matched = True
                    break
            if not matched:
                buckets.setdefault('其他材料', []).append(doc_path)
        logger.info(f"document buckets: {list(buckets.keys())}")

        # Use in-page JS to map each add button to its section title via DOM ancestors
        button_map = page.evaluate("""() => {
            const out = [];
            const sections = document.querySelectorAll('.uni-section');
            for (const sec of sections) {
                const titleEl = sec.querySelector('.uni-section__content-title');
                const title = titleEl ? (titleEl.textContent || '').trim() : '';
                const btn = sec.querySelector('.fd-file-container.fd-btn-add, .fd-btn-add');
                if (!btn) continue;
                const rect = btn.getBoundingClientRect();
                out.push({title, y: rect.y + rect.height/2, h: rect.height});
            }
            return out;
        }""")
        logger.info(f"button_map: {button_map}")

        # Fallback: 未准备诉状页面没有"起诉状"按钮，把起诉状文件归到"其他材料"
        if not any(('起诉状' in info['title'] or '诉状' in info['title']) for info in button_map):
            if '起诉状' in buckets:
                buckets.setdefault('其他材料', []).extend(buckets.pop('起诉状'))
                logger.info("页面无起诉状按钮，将起诉状归入其他材料")

        for i, info in enumerate(button_map):
            title = info['title']
            logger.info(f"button {i}: section '{title}'")
            bucket_key = None
            if '身份证明' in title:
                bucket_key = '身份证明'
            elif '委托' in title or '代理' in title:
                bucket_key = '委托书'
            elif '证据' in title:
                bucket_key = '证据'
            elif '送达' in title:
                bucket_key = '送达地址确认书'
            elif '其他' in title or '材料信息' in title:
                bucket_key = '其他材料'
            else:
                bucket_key = '其他材料'

            paths = buckets.get(bucket_key, [])
            if not paths:
                logger.info(f"skip button {i} ({bucket_key}): no documents")
                continue
            existing_paths = [p for p in paths if os.path.exists(p)]
            if not existing_paths:
                logger.warning(f"skip button {i} ({bucket_key}): no existing documents")
                continue
            try:
                # Find the section container and click its add button
                section = page.locator('.uni-section').filter(has_text=title).first
                btn = section.locator('.fd-file-container.fd-btn-add, .fd-btn-add').first
                for doc_path in existing_paths:
                    try:
                        with page.expect_event("filechooser", timeout=5000) as fc_info:
                            btn.click(timeout=3000)
                        fc = fc_info.value
                        fc.set_files(doc_path)
                        logger.info(f"selected {doc_path} for section {title}")
                    except Exception as e:
                        logger.warning(f"filechooser failed for {title} / {doc_path}: {e}")
                    self._wait(3)
                # Verify expected file names appear only in this section
                expected_names = [os.path.basename(p) for p in existing_paths]
                shown_titles = section.locator('.fd-com-upload-grid-container .fd-file-cursor').evaluate_all(
                    """elements => elements.map(e => {
                        const nameEl = e.querySelector('.fd-file-name');
                        const name = nameEl ? (nameEl.innerText || nameEl.textContent || '') : '';
                        const title = e.getAttribute('title') || '';
                        return title || name;
                    })"""
                )
                shown_names = [os.path.basename(t).split('-')[-1] for t in shown_titles if t]
                logger.info(f"section {title} expected {expected_names}, shown {shown_names}")
            except Exception as e:
                logger.warning(f"add button {i} ({title}) upload failed: {e}")

        self._save_state(page, "upload_after")
        # 进入完善案件信息
        self._click_page_bottom_next(page)
        try:
            page.wait_for_selector("text=完善案件信息", timeout=15000)
        except Exception:
            pass
        self._save_state(page, "party_form")

    def fill_party_form(self, page: Page, case_data: dict = None):
        """完善案件信息：标的金额、原告、被告、第三人、代理人"""
        logger.info("填写当事人信息...")
        if not case_data:
            case_data = getattr(self, '_case_data', {}) or {}

        # 1) 标的金额
        amount = case_data.get("amount", 0)
        try:
            self._fill_party_card_fields(page, {"标的金额（元）": str(amount)})
            logger.info(f"填写标的金额: {amount}")
        except Exception as e1:
            logger.warning(f"填标的金额失败: {e1}")
        self._wait(0.5)

        parties = case_data.get("parties", [])
        plaintiff = next((p for p in parties if p.get("party_type") == "原告"), {})
        defendant = next((p for p in parties if p.get("party_type") == "被告"), {})

        # 2) 编辑原告（已有默认卡片）
        if plaintiff:
            try:
                res = self._js_click_section_button(page, "原告信息", "编辑")
                if res.get('ok'):
                    logger.info("点击原告编辑")
                    self._wait(2)
                    self._fill_party_current_card(page, plaintiff, role="原告")
                    self._click_card_save(page)
                    self._wait(2)
                else:
                    logger.warning(f"未找到原告编辑按钮: {res}，尝试添加")
                    self._js_click_section_button(page, "原告信息", "添加自然人")
                    self._wait(2)
                    self._fill_party_current_card(page, plaintiff, role="原告")
                    self._click_card_save(page)
                    self._wait(2)
            except Exception as e:
                logger.warning(f"原告处理失败: {e}")

        # 3) 添加被告
        if defendant:
            try:
                self._js_click_section_button(page, "被告信息", "添加自然人")
                self._wait(2)
                self._fill_party_current_card(page, defendant, role="被告")
                self._click_card_save(page)
                self._wait(2)
            except Exception as e:
                logger.warning(f"添加被告失败: {e}")
        else:
            logger.warning("案件无被告信息，跳过")

        # 4) 第三人（若有）
        third_party = next((p for p in parties if p.get("party_type") == "第三人"), {})
        if third_party:
            try:
                self._js_click_section_button(page, "第三人信息", "添加自然人")
                self._wait(2)
                self._fill_party_current_card(page, third_party, role="第三人")
                self._click_card_save(page)
                self._wait(2)
            except Exception as e:
                logger.warning(f"添加第三人失败: {e}")
        else:
            self._cancel_empty_section(page, "第三人信息")

        # 5) 代理人（必填）
        agent = next((p for p in parties if p.get("party_type") == "代理人"), {})
        if not agent:
            agent = {
                "name": "测试代理人",
                "cert_no": "110101199003033456",
                "phone": "13600000003",
                "gender": "男",
                "nation": "汉族",
                "address": "北京市海淀区代理路1号"
            }
            logger.info("使用默认代理人信息")
        try:
            self._js_click_section_button(page, "代理人信息", "添加律师")
            self._wait(2)
            self._fill_party_current_card(page, agent, role="代理人")
            self._click_card_save(page)
            self._wait(2)
        except Exception as e:
            logger.warning(f"添加代理人失败: {e}")

        # 6) 下一步
        self._click_page_bottom_next(page)

    def _fill_party_current_card(self, page: Page, party: dict, role: str = "原告"):
        """根据当前卡片字段填写当事人信息"""
        values = {}
        if party.get("name"):
            values["姓名"] = party["name"]
        if party.get("cert_no") or party.get("idcard"):
            values["证件号码"] = party.get("cert_no") or party.get("idcard") or ""
        if party.get("phone"):
            values["联系电话"] = party["phone"]
        if party.get("address"):
            values["住所地（户籍所在地）"] = party["address"]
            values["经常居住地"] = party["address"]
        values["工作单位"] = party.get("work_unit", "无") or "无"
        values["职务"] = party.get("position", "其他") or "其他"
        if role in ("被告", "第三人", "代理人"):
            values["性别"] = party.get("gender", "男") or "男"
            values["国别或地区"] = party.get("country", "中国") or "中国"
            values["民族"] = party.get("nation", "汉族") or "汉族"
        logger.info(f"准备填写 {role} 字段: {list(values.keys())}")
        res = self._fill_party_card_fields(page, values)
        logger.info(f"{role} 填写结果: {res}")



    def _add_party_by_section(self, page: Page, section_title: str, party: dict, role: str = "原告", agent_type: str = "自然人"):
        """在指定区域点击添加按钮并填写"""
        btn_map = {
            "原告": "添加自然人",
            "被告": "添加自然人",
            "第三人": "添加自然人",
            "代理人": "添加律师",
        }
        btn_text = btn_map.get(role, "添加自然人")
        try:
            result = self._js_click_add_party(page, section_title, btn_text)
            if result.get('ok'):
                logger.info(f"点击 {section_title} {btn_text}")
            else:
                logger.warning(f"点击 {section_title} 添加按钮失败: {result}")
        except Exception as e:
            logger.warning(f"点击 {section_title} 添加按钮异常: {e}")
        self._wait(2)
        self._fill_party_dialog(page, party, role=role)


    def _fill_party_dialog(self, page: Page, party: dict, role: str = "原告"):
        """在当事人编辑/添加弹窗中填写完整字段"""
        # 通用字段
        self._fill_field_by_label(page, "姓名", party.get("name", ""), role=role)
        self._select_dropdown_by_label(page, "证件类型", "居民身份证", role=role)
        self._fill_field_by_label(page, "证件号码", party.get("cert_no", party.get("idcard", "")), role=role)

        if role in ("原告", "被告", "第三人"):
            self._select_dropdown_by_label(page, "性别", party.get("gender", "男") or "男", role=role)
            self._select_dropdown_by_label(page, "民族", party.get("nation", "汉族") or "汉族", role=role)
            self._fill_field_by_label(page, "工作单位", "无", role=role)
            self._select_dropdown_by_label(page, "职务", "其他", role=role)
            self._fill_field_by_label(page, "联系电话", party.get("phone", ""), role=role)
            self._fill_field_by_label(page, "住所地", party.get("address", ""), role=role)
            self._fill_field_by_label(page, "经常居住地", party.get("address", ""), role=role)
            if role == "原告":
                self._upload_in_card(page, "收款账户确认书", party.get("bank_file"))
        elif role == "代理人":
            # 代理人字段：证件号码、执业证号、单位、联系电话
            self._fill_field_by_label(page, "执业证号", party.get("license_no", ""), role=role)
            self._fill_field_by_label(page, "工作单位", "无", role=role)
            self._fill_field_by_label(page, "联系电话", party.get("phone", ""), role=role)

        self._click_card_save(page)


    def _cancel_empty_section(self, page: Page, section_title: str):
        """如果某区域默认展开了空白编辑表单，尝试取消"""
        try:
            loc = page.locator("text=" + section_title).first
            if loc.count() and loc.is_visible():
                section = loc.locator("xpath=../../..")
                cancel = section.locator("text=取消").first
                if cancel.count() and cancel.is_visible():
                    cancel.click(timeout=3000)
                    logger.info(f"取消 {section_title} 空白表单")
                    self._wait(0.5)
        except Exception as e:
            logger.debug(f"取消 {section_title} 表单忽略: {e}")


    # ------------------------------------------------------------------
    # 通用 JS 辅助函数：在页面内根据可见文本/类名操作 DOM
    # ------------------------------------------------------------------
    def _js_click_text(self, page: Page, text: str, exact: bool = False, tag_filter: str = None, timeout: int = 5000) -> dict:
        """用 JS 点击页面上可见文本匹配的第一个元素"""
        script = """(args) => {
            const text = args.text, exact = args.exact, tagFilter = args.tagFilter;
            function isVisible(el) {
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0 && r.top >= -r.height && r.left >= -r.width;
            }
            let selector = tagFilter || 'uni-view, uni-button, button, div, span, a';
            let all = document.querySelectorAll(selector);
            // 1) exact match
            for (const el of all) {
                if (!isVisible(el)) continue;
                const t = (el.innerText || '').trim();
                if (t === text) { el.click(); return {ok: true, text, exact: true, tag: el.tagName}; }
            }
            if (exact) return {err: 'not found exact', text};
            // 2) contains
            for (const el of all) {
                if (!isVisible(el)) continue;
                const t = (el.innerText || '').trim();
                if (t.includes(text)) { el.click(); return {ok: true, text, contains: true, tag: el.tagName}; }
            }
            // 3) fallback: any element with text node
            all = document.querySelectorAll('*');
            for (const el of all) {
                if (!isVisible(el)) continue;
                for (const node of el.childNodes) {
                    if (node.nodeType === 3 && (node.textContent || '').trim().includes(text)) {
                        el.click(); return {ok: true, text, fallback: true, tag: el.tagName};
                    }
                }
            }
            return {err: 'not found', text};
        }"""
        return page.evaluate(script, {"text": text, "exact": exact, "tagFilter": tag_filter})


    def _fill_party_card_fields(self, page: Page, values: dict) -> dict:
        """Fill all visible fields in the currently opened party card using Playwright."""
        results = {}
        for label, value in values.items():
            if value is None or str(value) == "":
                continue
            try:
                item = page.locator(".uni-forms-item, uni-forms-item, .fd-com-form-item").filter(has_text=label).filter(has=page.locator("input, .uni-data-tree, .uni-select, .uni-picker, .uni-data-tree-input, .input-value")).last
                if item.count() == 0:
                    results[label] = {"err": "not found"}
                    continue
                tree = item.locator(".uni-data-tree, .uni-select, .uni-picker, .uni-data-tree-input, .input-value").first
                if tree.count() > 0:
                    tree.click(timeout=5000)
                    self._wait(0.8)
                    chosen_text = page.evaluate(
                        r"""(value) => {
                            function isVisible(el) { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; }
                            const popups = Array.from(document.querySelectorAll('.uni-data-tree-popup, .uni-select-popup, .uni-picker-container, .uni-popup, .uni-list, .uni-data-pickerview, .uni-picker')).filter(isVisible);
                            let best = null, bestText = '';
                            for (const pop of popups) {
                                const elems = Array.from(pop.querySelectorAll('.fd-item, .item-text, .uni-picker-item, .uni-list-item, .uni-picker-view-group-item'));
                                for (const el of elems) {
                                    if (!isVisible(el)) continue;
                                    const t = (el.innerText || '').replace(/\s+/g, ' ').trim();
                                    if (!t) continue;
                                    if (t === value) { best = el; bestText = t; break; }
                                    if (!best && t.includes(value)) { best = el; bestText = t; }
                                }
                                if (best && bestText === value) break;
                            }
                            if (best) { best.click(); return bestText; }
                            return null;
                        }""", str(value)
                    )
                    if chosen_text:
                        results[label] = {"ok": True, "text": chosen_text}
                    else:
                        results[label] = {"err": "option not found", "value": value}
                    self._wait(0.3)
                else:
                    inp = item.locator("input.uni-input-input, input.uni-easyinput__content-input, textarea.uni-easyinput__content-textarea, input").first
                    if inp.count() == 0:
                        results[label] = {"err": "no input"}
                        continue
                    if inp.is_disabled():
                        results[label] = {"ok": True, "skipped": "disabled", "value": str(value)}
                        continue
                    val = str(value)
                    inp.fill(val, timeout=5000)
                    inp.evaluate(
                        """(el, value) => {
                            const d = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value') || Object.getOwnPropertyDescriptor(Object.getPrototypeOf(el), 'value');
                            if (d && d.set) d.set.call(el, value);
                            el.dispatchEvent(new Event('input', {bubbles: true}));
                            el.dispatchEvent(new Event('change', {bubbles: true}));
                            el.dispatchEvent(new Event('blur', {bubbles: true}));
                        }""", val
                    )
                    results[label] = {"ok": True, "value": val}
            except Exception as e:
                results[label] = {"err": str(e), "value": value}
        return results




    def _click_card_save(self, page: Page) -> dict:
        """Click the save button of the currently opened party card and wait for close."""
        try:
            sel = "uni-button:visible:has-text('保存'), button:visible:has-text('保存'), .uni-button--primary:visible, .fd-com-btn-primary:visible, .fd-com-btn-container >> text=保存"
            btns = page.locator(sel)
            cnt = btns.count()
            btn = None
            for i in range(cnt):
                b = btns.nth(i)
                txt = (b.inner_text(timeout=1000) or '').replace('\n', '').strip()
                if '保存' in txt and '取消' not in txt:
                    btn = b
                    break
            if not btn:
                all = page.locator("text=保存")
                for i in range(all.count()):
                    b = all.nth(i)
                    if b.is_visible() and (b.inner_text(timeout=1000) or '').strip() == '保存':
                        btn = b
                        break
            if not btn:
                return {"err": "save button not found"}
            btn.click(timeout=5000)
            self._wait(1.5)
            for _ in range(20):
                if page.locator("uni-button:visible:has-text('保存'), button:visible:has-text('保存')").count() == 0:
                    break
                self._wait(0.3)
            return {"ok": True}
        except Exception as e:
            return {"err": str(e)}



    def _js_click_section_button(self, page: Page, section_title: str, btn_text: str) -> dict:
        return page.evaluate(r"""(args) => {
            const sectionTitle = args.sectionTitle, btnText = args.btnText;
            function isVisible(el) { if (!el) return false; const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; }
            const all = Array.from(document.querySelectorAll('uni-section, .uni-section, section, uni-view, div')).filter(isVisible);
            let section = null;
            for (const el of all) {
                const t = (el.innerText || '').replace(/\s+/g, ' ').trim();
                if (t.includes(sectionTitle)) {
                    if (el.tagName === 'UNI-SECTION' || el.className.includes('uni-section') && !el.className.includes('uni-section-header')) {
                        section = el; break;
                    }
                    if (!section) section = el;
                }
            }
            if (!section) return {err: 'section not found', sectionTitle};
            // if we picked a header, walk up to the section container
            if (section.className.includes('uni-section-header') || section.tagName === 'UNI-VIEW' && section.className.includes('header')) {
                let p = section.parentElement;
                while (p && !p.className.includes('uni-section') && p.tagName !== 'UNI-SECTION') p = p.parentElement;
                section = p || section;
            }
            let target = null;
            if (btnText.includes('编辑')) {
                const icons = Array.from(section.querySelectorAll('.uniui-compose, .fd-sscyr-option-pc-icon, .fd-sscyr-edit-icon')).filter(isVisible);
                if (icons.length) target = icons[0];
            }
            if (!target) {
                // add buttons often have class fd-sscyr-add-btn; prefer those
                let addBtns = Array.from(section.querySelectorAll('.fd-sscyr-add-btn')).filter(e => isVisible(e) && (e.innerText || '').trim().includes(btnText));
                if (!addBtns.length) {
                    addBtns = Array.from(section.querySelectorAll('uni-view, view, uni-button, button, span')).filter(e => isVisible(e) && (e.innerText || '').trim() === btnText);
                }
                if (addBtns.length) {
                    target = addBtns.sort((a, b) => { const ra = a.getBoundingClientRect(), rb = b.getBoundingClientRect(); return (ra.width * ra.height) - (rb.width * rb.height); })[0];
                }
            }
            if (!target) return {err: 'btn not found in section', sectionTitle, btnText, sectionClass: section.className};
            target.click();
            return {ok: true, sectionTitle, btnText, clicked: (target.innerText || '').replace(/\s+/g, ' ').trim(), className: target.className};
        }""", {"sectionTitle": section_title, "btnText": btn_text})





    def _js_find_form_item(self, page: Page, label: str) -> dict:
        """用 JS 找到包含 label 的 uni-forms-item 并返回标签和可输入元素信息"""
        script = """(label) => {
            function isVisible(el) {
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
            }
            const items = document.querySelectorAll('uni-forms-item, .uni-forms-item, .fd-com-form-item');
            for (const item of items) {
                if (!isVisible(item)) continue;
                const labelEl = item.querySelector('.uni-forms-item__label, .uni-forms-item__title, .fd-form-label, .label');
                if (!labelEl) continue;
                const t = (labelEl.innerText || '').trim();
                if (t.includes(label)) {
                    const inp = item.querySelector('input.uni-input-input, input.uni-easyinput__content-input, uni-input input, textarea, .uni-easyinput__content-input');
                    const trigger = item.querySelector('.uni-data-tree-input, .uni-input, .uni-easyinput, .uni-select, .fd-select-area');
                    return {ok: true, labelText: t, hasInput: !!inp, hasTrigger: !!trigger, inputTag: inp ? inp.tagName : null, inputCls: inp ? inp.className : null};
                }
            }
            return {err: 'item not found', label};
        }"""
        return page.evaluate(script, label)

    def _js_fill_by_label(self, page: Page, label: str, value: str) -> dict:
        """用 JS 在 uni-forms-item 中填写 input/textarea"""
        script = """(args) => {
            const label = args.label, value = String(args.value);
            function isVisible(el) {
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
            }
            function setNativeValue(el, value) {
                const descriptor = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value') ||
                                     Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value');
                if (descriptor && descriptor.set) {
                    descriptor.set.call(el, value);
                } else {
                    el.value = value;
                }
                el.dispatchEvent(new Event('input', {bubbles: true}));
                el.dispatchEvent(new Event('change', {bubbles: true}));
                el.dispatchEvent(new Event('blur', {bubbles: true}));
            }
            const items = document.querySelectorAll('uni-forms-item, .uni-forms-item, .fd-com-form-item');
            for (const item of items) {
                if (!isVisible(item)) continue;
                const labelEl = item.querySelector('.uni-forms-item__label, .uni-forms-item__title, .fd-form-label, .label');
                if (!labelEl) continue;
                const t = (labelEl.innerText || '').trim();
                if (t.includes(label)) {
                    const input = item.querySelector('input.uni-input-input, input.uni-easyinput__content-input, uni-input input, textarea, .uni-easyinput__content-input');
                    if (input) {
                        input.focus();
                        setNativeValue(input, value);
                        return {ok: true, label: t, value};
                    }
                    // fallback: any input in item
                    const anyInput = item.querySelector('input, textarea');
                    if (anyInput) {
                        anyInput.focus();
                        setNativeValue(anyInput, value);
                        return {ok: true, label: t, value, fallback: true};
                    }
                    return {err: 'no input in item', label: t};
                }
            }
            return {err: 'label not found', label};
        }"""
        return page.evaluate(script, {"label": label, "value": value})

    def _js_select_by_label(self, page: Page, label: str, value: str) -> dict:
        """用 JS 点击 label 对应的下拉触发器并选择选项"""
        script = """(args) => {
            const label = args.label, value = args.value;
            function isVisible(el) {
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
            }
            function sleep(ms) { const s = Date.now(); while (Date.now() - s < ms) {} }
            function findItem() {
                const items = document.querySelectorAll('uni-forms-item, .uni-forms-item, .fd-com-form-item');
                for (const item of items) {
                    if (!isVisible(item)) continue;
                    const labelEl = item.querySelector('.uni-forms-item__label, .uni-forms-item__title, .fd-form-label, .label');
                    if (!labelEl) continue;
                    const t = (labelEl.innerText || '').trim();
                    if (t.includes(label)) return item;
                }
                return null;
            }
            const item = findItem();
            if (!item) return {err: 'item not found', label};
            // 1) 点触发器（content 区域）
            let trigger = item.querySelector('.uni-data-tree-input, .uni-input, .uni-easyinput, .uni-select, .fd-select-area, .uni-forms-item__content');
            if (!trigger) trigger = item;
            trigger.click();
            sleep(300);
            // 2) 尝试打开弹层（有些下拉需要再点一次）
            const content = item.querySelector('.uni-forms-item__content');
            if (content) content.click();
            sleep(200);
            // 3) 寻找选项
            const optionSelectors = '.uni-picker-item, .uni-data-tree-popup-item, .uni-select-item, .uni-combox-item, .uni-picker-container .uni-picker-item, .uni-picker-custom .uni-picker-item, .uni-data-pickerview-item, .uni-data-tree-item';
            for (let attempt = 0; attempt < 15; attempt++) {
                const opts = document.querySelectorAll(optionSelectors);
                for (const opt of opts) {
                    if ((opt.innerText || '').trim() === value) {
                        opt.click();
                        return {ok: true, label, value};
                    }
                }
                // 模糊匹配
                for (const opt of opts) {
                    if ((opt.innerText || '').trim().includes(value)) {
                        opt.click();
                        return {ok: true, label, value, contains: true};
                    }
                }
                sleep(200);
            }
            return {err: 'option not found', label, value};
        }"""
        return page.evaluate(script, {"label": label, "value": value})


    def _js_click_add_party(self, page: Page, section_title: str, btn_text: str) -> dict:
        """用 JS 在指定区域点击添加按钮"""
        script = """(args) => {
            const sectionTitle = args.sectionTitle, btnText = args.btnText;
            function isVisible(el) {
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
            }
            // 1) 找到区域标题
            let section = null;
            const all = document.querySelectorAll('uni-view, div, section');
            for (const el of all) {
                if (!isVisible(el)) continue;
                const t = (el.innerText || '').trim();
                if (t === sectionTitle || t.includes(sectionTitle)) {
                    section = el; break;
                }
            }
            if (!section) return {err: 'section not found', sectionTitle};
            // 2) 在区域内或后面找按钮
            // 优先区域内
            let addBtn = null;
            const children = section.querySelectorAll('uni-view, uni-button, button, div, span');
            for (const el of children) {
                if (!isVisible(el)) continue;
                const t = (el.innerText || '').trim();
                if (t === btnText || t.includes(btnText)) { addBtn = el; break; }
            }
            // 若找不到，找标题右侧兄弟节点
            if (!addBtn) {
                let sibling = section.nextElementSibling;
                while (sibling) {
                    const t = (sibling.innerText || '').trim();
                    if (t.includes(btnText)) { addBtn = sibling; break; }
                    sibling = sibling.nextElementSibling;
                }
            }
            // 最后在整个页面找包含文本的按钮
            if (!addBtn) {
                for (const el of all) {
                    if (!isVisible(el)) continue;
                    const t = (el.innerText || '').trim();
                    if (t === btnText || t.includes(btnText)) { addBtn = el; break; }
                }
            }
            if (!addBtn) return {err: 'button not found', sectionTitle, btnText};
            addBtn.click();
            return {ok: true, sectionTitle, btnText, clickedText: addBtn.innerText || ''};
        }"""
        return page.evaluate(script, {"sectionTitle": section_title, "btnText": btn_text})

    def _js_click_bottom_next(self, page: Page) -> dict:
        """用 JS 点击页面底部下一步（只在底部导航区）"""
        return page.evaluate("""() => {
            function isVisible(el) {
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
            }
            window.scrollTo(0, document.body.scrollHeight);
            function sleep(ms) { const s = Date.now(); while (Date.now() - s < ms) {} }
            sleep(300);
            // 1) 在 fd-com-btn-container 内的下一步
            const containers = document.querySelectorAll('.fd-com-btn-container');
            for (const c of containers) {
                if (!isVisible(c)) continue;
                const r = c.getBoundingClientRect();
                if (r.top < window.innerHeight - 150) {
                    const btns = c.querySelectorAll('uni-button, button');
                    for (const b of btns) {
                        const t = (b.innerText || '').trim();
                        if (t === '下一步' || t.includes('下一步')) { b.click(); return {ok: true, text: t, container: true}; }
                    }
                }
            }
            // 2) 页面底部 y > 500 的下一步
            const all = document.querySelectorAll('uni-button, button');
            const candidates = [];
            for (const b of all) {
                if (!isVisible(b)) continue;
                const t = (b.innerText || '').trim();
                if (t === '下一步' || t.includes('下一步')) {
                    const r = b.getBoundingClientRect();
                    candidates.push({b, y: r.y, area: r.width * r.height});
                }
            }
            candidates.sort((a, b) => b.y - a.y); // 最下面的
            if (candidates.length) { candidates[0].b.click(); return {ok: true, text: candidates[0].b.innerText, y: candidates[0].y}; }
            return {err: 'next not found'};
        }""")

    def _fill_field_by_label(self, page: Page, label: str, value: str, role: str = None) -> bool:
        """根据 label 在 uni-forms-item 中填写 input/textarea"""
        if not value:
            return True
        try:
            # 优先支持 role-specific label（如 代理人证件号码）
            labels_to_try = [label]
            if role == "代理人":
                if label == "证件号码": labels_to_try = ["代理人证件号码", "证件号码"]
                if label == "证件类型": labels_to_try = ["代理人证件类型", "证件类型"]
                if label == "工作单位": labels_to_try = ["单位", "工作单位"]
            if label == "工作单位":
                labels_to_try = ["工作单位", "单位"]
            for lbl in labels_to_try:
                result = self._js_fill_by_label(page, lbl, value)
                if result.get('ok'):
                    logger.info(f"JS填写 {lbl}: {value}")
                    return True
            logger.warning(f"填写 {label} 失败: {result}")
            return False
        except Exception as e:
            logger.warning(f"填写 {label} 异常: {e}")
            return False


    def _select_dropdown_by_label(self, page: Page, label: str, value: str, role: str = None) -> bool:
        """根据 label 选择下拉选项"""
        try:
            labels_to_try = [label]
            if role == "代理人":
                if label == "证件类型": labels_to_try = ["代理人证件类型", "证件类型"]
            result = self._js_select_by_label(page, labels_to_try[0], value)
            if result.get('ok'):
                logger.info(f"选择 {label}: {value}")
                return True
            logger.warning(f"选择 {label} 失败: {result}")
            return False
        except Exception as e:
            logger.warning(f"选择 {label} 异常: {e}")
            return False


    def _upload_in_card(self, page: Page, label: str, file_path: str = None):
        """在当事人卡片内上传指定文件（通过寻找隐藏 input[type=file] 触发）"""
        if not file_path or not os.path.exists(file_path):
            base_dir = Path(__file__).resolve().parent.parent.parent
            candidates = [
                base_dir / "documents" / "cases" / "_default" / f"{label}.pdf",
                base_dir / "src" / "documents" / "cases" / "_default" / f"{label}.pdf",
            ]
            for c in candidates:
                if c.exists():
                    file_path = str(c)
                    break
        if not file_path or not os.path.exists(file_path):
            logger.warning(f"跳过上传 {label}：无文件")
            return
        try:
            # 尝试用 JS 定位 label 附近的 input[type=file]
            input_info = page.evaluate("""(label) => {
                function isVisible(el) {
                    const r = el.getBoundingClientRect();
                    return r.width > 0 && r.height > 0;
                }
                // 1) 找包含 label 的 card/section
                let container = null;
                const all = document.querySelectorAll('*');
                for (const el of all) {
                    if (!isVisible(el)) continue;
                    if ((el.innerText || '').trim().includes(label)) { container = el; break; }
                }
                // 2) 在 container 或页面里找 input[type=file]
                let inputs = [];
                if (container) {
                    inputs = Array.from(container.querySelectorAll('input[type=file]')).filter(i => i.offsetParent || i.style.display !== 'none');
                }
                if (!inputs.length) {
                    inputs = Array.from(document.querySelectorAll('input[type=file]')).filter(i => isVisible(i) || i.style.position === 'absolute');
                }
                // 3) 若找到，返回可复用的 selector（CSS 选择器路径）
                if (inputs.length) {
                    const inp = inputs[0];
                    // build unique-ish selector
                    let path = inp.tagName.toLowerCase() + '[type="file"]';
                    if (inp.id) path = '#' + inp.id;
                    else if (inp.className) path = inp.tagName.toLowerCase() + '.' + inp.className.split(' ').join('.');
                    return {found: true, path: path, count: inputs.length};
                }
                // 4) 若只有全局隐藏 input，返回最后一个（通常就是页面级文件上传）
                const hidden = Array.from(document.querySelectorAll('input[type=file]'));
                if (hidden.length) {
                    return {found: true, hidden: true, count: hidden.length};
                }
                return {err: 'no file input', label};
            }""", label)
            logger.info(f"上传定位结果: {input_info}")
            if input_info.get('found'):
                # 如果只有一个全局隐藏 input，可能直接点击“上传”按钮触发 filechooser，然后用 Playwright 拦截
                if input_info.get('hidden') and input_info.get('count') == 1:
                    # 点击 label 所在卡片的上传按钮/加号
                    click_res = self._js_click_text(page, label)
                    logger.info(f"点击上传区: {click_res}")
                    fc = page.wait_for_event("filechooser", timeout=5000)
                    fc.set_files(file_path)
                else:
                    # 有特定 input，直接设置文件
                    page.set_input_files(input_info['path'], file_path)
                logger.info(f"上传 {label}: {file_path}")
                self._wait(2)
                return
            else:
                logger.warning(f"未找到上传输入框: {input_info}")
        except Exception as e:
            logger.warning(f"上传 {label} 失败: {e}")



    def _click_page_bottom_next(self, page: Page) -> bool:
        """滚动到底部并点击页面底部下一步，自动处理签名提示弹窗"""
        try:
            result = self._js_click_bottom_next(page)
            if result.get('ok'):
                logger.info("点击页面底部下一步")
                try:
                    page.wait_for_load_state("networkidle", timeout=10000)
                except Exception:
                    pass
                self._wait(2)
                self._dismiss_signature_popup(page)
                return True
            logger.warning(f"点击页面底部下一步失败: {result}")
            return False
        except Exception as e:
            logger.warning(f"点击页面底部下一步异常: {e}")
            return False

    def _dismiss_signature_popup(self, page: Page) -> bool:
        """点击签名/提示类弹窗的确定按钮"""
        try:
            for text in ["确定", "我知道了", "确认"]:
                candidates = page.locator(f"uni-button:visible:has-text('{text}'), button:visible:has-text('{text}'), .uni-button:visible:has-text('{text}'), .uni-modal__btn:visible:has-text('{text}'), .uni-modal__btn_primary:visible:has-text('{text}')")
                for i in range(candidates.count()):
                    btn = candidates.nth(i)
                    if btn.is_visible():
                        btn.click(timeout=3000)
                        logger.info(f"点击弹窗按钮: {text}")
                        self._wait(2)
                        self._dismiss_signature_popup(page)
                        return True
            return False
        except Exception as e:
            logger.debug(f"弹窗处理异常: {e}")
            return False
        except Exception as e:
            logger.debug(f"弹窗处理异常: {e}")
            return False
        except Exception as e:
            logger.debug(f"弹窗处理异常: {e}")
            return False
        except Exception as e:
            logger.debug(f"弹窗处理异常: {e}")
            return False
        except Exception as e:
            logger.warning(f"点击页面底部下一步异常: {e}")
            return False


    def fill_claims_and_facts(self, page: Page, case_data: dict = None) -> None:
        """填写诉讼请求和事实与理由"""
        if not case_data:
            case_data = getattr(self, '_case_data', {}) or {}
        claim = case_data.get('claim', case_data.get('claims', '请求被告支付欠款人民币100000元及利息。'))
        facts = case_data.get('facts', case_data.get('fact_reason', '原被告之间存在买卖合同关系，原告已履行交货义务，被告未支付货款。'))
        # 诉讼请求
        for label in ['诉讼请求1', '诉讼请求', '诉讼']:
            try:
                item = page.locator('.uni-forms-item, uni-forms-item, .fd-com-form-item').filter(has_text=label).filter(has=page.locator('textarea, input')).last
                if item.count() == 0:
                    continue
                inp = item.locator('textarea, input').first
                inp.fill(str(claim), timeout=5000)
                logger.info(f'填写诉讼请求: {claim[:30]}')
                break
            except Exception as e:
                logger.warning(f'填写诉讼请求 {label} 失败: {e}')
        # 事实与理由
        for label in ['事实与理由', '事实理由']:
            try:
                item = page.locator('.uni-forms-item, uni-forms-item, .fd-com-form-item').filter(has_text=label).filter(has=page.locator('textarea, input')).last
                if item.count() == 0:
                    continue
                inp = item.locator('textarea, input').first
                inp.fill(str(facts), timeout=5000)
                logger.info(f'填写事实与理由: {facts[:30]}')
                break
            except Exception as e:
                logger.warning(f'填写事实与理由 {label} 失败: {e}')
        self._wait(1)


    def complete_case_info_and_preview(self, page: Page, case_data: dict = None) -> bool:
        """从完善案件信息（诉讼请求/事实理由）填写并推进到预览和提交页面，处理签名弹窗"""
        if not case_data:
            case_data = getattr(self, '_case_data', {}) or {}
        self.fill_claims_and_facts(page, case_data)
        self._click_page_bottom_next(page)
        self._wait(1)
        # handle signature list if it appears after the initial notice popup
        if self._has_text(page, '我的签字') or page.locator(".fd-com-layer-header:visible:has-text('我的签字')").count():
            self._select_signature(page)
            self._wait(2)
            # after selecting signature, document preview is shown; click next to go to preview/submit
            self._click_page_bottom_next(page)
            self._wait(2)
        return self._has_text(page, '预览和提交') or self._has_text(page, '提交立案')

    def _select_signature(self, page: Page) -> bool:
        """选择第一个可用签名并点击引入签章"""
        try:
            cards = page.locator('.fd-com-card-list .fd-com-card').locator(':visible')
            if cards.count():
                cards.first.click(timeout=5000)
                logger.info('选择第一个签名卡片')
                self._wait(1)
            import_btn = page.locator("uni-button:visible:has-text('引入签章')")
            if import_btn.count():
                import_btn.first.click(timeout=5000)
                logger.info('点击引入签章')
                self._wait(3)
                return True
            return False
        except Exception as e:
            logger.warning(f'选择签名异常: {e}')
            return False


    def submit_case(self, page: Page, case_data: dict = None, dry_run: bool = False) -> dict:
        logger.info("提交立案申请..." if not dry_run else "dry_run: 提交前停止")
        self._case_data = case_data or getattr(self, '_case_data', None) or {}
        self._save_state(page, "submit_before")

        # 1) 如果当前还在完善案件信息，推进到预览和提交
        if self._has_text(page, "完善案件信息"):
            logger.info("当前在完善案件信息页面，先填写并推进到预览")
            if not self.complete_case_info_and_preview(page, self._case_data):
                logger.warning("未能进入预览和提交步骤")
                self._save_state(page, "not_preview")
                return {"status": "failed", "message": "填写后仍未进入预览和提交页面"}

        # 2) 检查是否真的到了预览和提交步骤
        if not (self._has_text(page, "预览和提交") or self._has_text(page, "提交立案")):
            logger.warning("未能进入预览和提交步骤")
            self._save_state(page, "not_preview")
            return {"status": "failed", "message": "填写后仍未进入预览和提交页面"}

        if dry_run:
            logger.info("dry_run: 已到达预览和提交页面，停止提交")
            self._save_state(page, "dry_run_preview")
            return {"success": True, "case_id": "", "message": "dry_run: 已到达预览和提交页面，未提交"}

        # 3) 尝试真实提交
        submitted = False
        case_id = ""
        message = "已走到预览和提交步骤，但未触发真实提交"
        try:
            # 3) 尝试点击提交按钮（优先使用 JS，避免自定义元素选择器问题）
            # 在“预览和提交”页，按钮通常是“下一步”，点击后进入确认弹窗
            result = page.evaluate("""() => {
                const btns = document.querySelectorAll('uni-button, button, .uni-modal__btn');
                for (const b of btns) {
                    const t = (b.innerText || '').trim();
                    if (t === '提交' || t === '确认提交' || t === '立即提交') { b.click(); return 'clicked ' + t; }
                    if (t === '下一步') { b.click(); return 'clicked next'; }
                }
                return null;
            }""")
            if result:
                logger.info(f"submit action: {result}")
                submitted = True
                self._wait(5)
            # 3.5) 如果出现确认弹窗，点击“确认提交”或“确定”
            if submitted:
                confirm_res = page.evaluate("""() => {
                    const btns = document.querySelectorAll('uni-button, button, .uni-modal__btn, .uni-actionsheet__cell');
                    for (const b of btns) {
                        const t = (b.innerText || '').trim();
                        if (t === '确认提交' || t === '确定' || t === '确认' || t === 'OK') { b.click(); return 'clicked ' + t; }
                    }
                    return null;
                }""")
                if confirm_res:
                    logger.info(f"confirmation {confirm_res}")
                    self._wait(8)

            # 4) 处理先行调解弹窗
            self._handle_mediation_dialog(page)

            # 5) 校验是否真正进入成功页，避免停留在“预览和提交”或被打回“上传诉讼材料”
            if self._is_on_success_page(page):
                self._save_state(page, "submitted_success")
                return {"success": True, "case_id": "", "message": "立案申请已提交成功"}

            # 5.5) 如果提交后被校验打回，当前步骤会回到上传/完善/预览，不视为成功
            active = self._get_active_step_text(page)
            if active in ('上传诉讼材料', '完善案件信息', '预览和提交'):
                logger.warning(f"提交未通过校验，当前步骤: {active}")
                self._save_state(page, "submit_validation_failed")
                return {"success": False, "case_id": "", "message": f"提交未通过校验，停留在 {active}"}

            # 5) 处理手机验证码（目前只检测，不填写真实验证码）
            if self._has_verification_dialog(page):
                logger.warning("出现验证码/人脸验证弹窗，需要人工处理")
                self._save_state(page, "verification_required")
                return {"success": False, "case_id": "", "message": "提交需要验证码/人脸验证，暂停"}

            content = page.content()
            m = re.search(r'案件编号[：:]\s*([A-Za-z0-9\-]+)', content)
            if not m:
                m = re.search(r'案号[：:]\s*([A-Za-z0-9\-]+)', content)
            if not m:
                m = re.search(r'流水号[：:]\s*([A-Za-z0-9\-]+)', content)
            if m:
                case_id = m.group(1)
            if not submitted:
                message = "未找到提交按钮，停留在预览页面"
                self._save_state(page, "not_submitted")
                return {"success": False, "case_id": case_id, "message": message}
            message = "已触发提交，但未能确认成功页"
        except Exception as e:
            logger.warning(f"提交时异常: {e}")
            message = f"提交异常: {e}"

        self._save_state(page, "submitted_unconfirmed")
        return {"success": False, "case_id": case_id, "message": message}

    def _handle_mediation_dialog(self, page: Page) -> bool:
        """处理先行调解弹窗：默认不同意"""
        try:
            # Use JS to reliably click the disagree button inside the mediation dialog
            result = page.evaluate("""() => {
                const btns = document.querySelectorAll('uni-button, button, .uni-modal__btn, .fd-com-btn-container uni-button');
                for (const b of btns) {
                    const t = (b.innerText || '').trim();
                    if (t.includes('不同意进行先行调解')) { b.click(); return 'clicked ' + t; }
                }
                return 'not found';
            }""")
            if result and result.startswith('clicked'):
                logger.info(f"点击调解选项: 不同意进行先行调解")
                self._wait(3)
                return True
            return False
        except Exception as e:
            logger.debug(f"调解弹窗处理异常: {e}")
            return False
        except Exception as e:
            logger.debug(f"调解弹窗处理异常: {e}")
            return False

    def _has_verification_dialog(self, page: Page) -> bool:
        """检测是否出现验证码、人脸识别或短信验证弹窗"""
        try:
            texts = ["验证码", "短信验证", "人脸识别", "扫码验证", "确认提交"]
            for t in texts:
                if self._has_text(page, t):
                    # 确认是输入/验证类弹窗
                    if page.locator("input[placeholder*=验证码], input[placeholder*=短信], .uni-modal:visible").count():
                        return True
            return False
        except Exception:
            return False


    def check_status(self, page: Page, case_id: str) -> dict:
        return {
            "case_id": case_id,
            "status": "未实现",
            "update_time": "",
            "court_code": self.court_code,
            "court_name": self.court_name
        }
