from playwright.sync_api import Page, Locator
from loguru import logger
from config import settings

class SmartWait:
    # 智能等待策略
    
    def __init__(self, page: Page, timeout: int = None):
        self.page = page
        self.timeout = timeout or settings.BROWSER_TIMEOUT
    
    def wait_for_element(self, selector: str, state: str = "visible"):
        # 等待元素出现
        logger.debug(f"等待元素: {selector}, 状态: {state}")
        self.page.wait_for_selector(selector, state=state, timeout=self.timeout)
    
    def wait_for_stable(self, selector: str, max_checks: int = 10):
        # 等待元素稳定(不再移动)
        logger.debug(f"等待元素稳定: {selector}")
        element = self.page.locator(selector)
        element.wait_for(state="visible")
        
        # 检查元素位置是否稳定
        prev_box = None
        for i in range(max_checks):
            box = element.bounding_box()
            if prev_box and box == prev_box:
                logger.debug(f"元素已稳定，检查次数: {i+1}")
                break
            prev_box = box
            self.page.wait_for_timeout(100)
    
    def wait_for_ajax(self):
        # 等待AJAX请求完成
        logger.debug("等待AJAX请求完成...")
        self.page.wait_for_load_state("networkidle")
    
    def wait_for_text(self, selector: str, text: str):
        # 等待特定文本出现
        logger.debug(f"等待文本: {text} 出现在: {selector}")
        self.page.locator(selector).filter(has_text=text).wait_for(timeout=self.timeout)
    
    def wait_for_navigation(self, url_pattern: str = None):
        # 等待页面导航完成
        if url_pattern:
            logger.debug(f"等待导航到: {url_pattern}")
            self.page.wait_for_url(url_pattern, timeout=self.timeout)
        else:
            logger.debug("等待导航完成...")
            self.page.wait_for_load_state("load")
    
    def wait_for_download(self):
        # 等待下载完成
        logger.debug("等待下载完成...")
        with self.page.expect_download(timeout=self.timeout) as download_info:
            pass
        return download_info.value
