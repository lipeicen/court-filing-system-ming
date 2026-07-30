from queue import Queue, Empty
from threading import Lock
from playwright.sync_api import sync_playwright, Browser
from loguru import logger
from config import settings

class BrowserPool:
    # 浏览器连接池
    
    def __init__(self, max_size: int = None, headless: bool = None):
        self.max_size = max_size or settings.BROWSER_POOL_SIZE
        self.headless = headless if headless is not None else settings.BROWSER_HEADLESS
        self._pool = Queue(maxsize=self.max_size)
        self._lock = Lock()
        self._count = 0
        self._playwright = None
        logger.info(f"初始化浏览器池，大小: {self.max_size}, 无头模式: {self.headless}")
    
    def _init_playwright(self):
        # 初始化Playwright
        if not self._playwright:
            self._playwright = sync_playwright().start()
            logger.info("Playwright 已初始化")
    
    def acquire(self) -> Browser:
        # 获取浏览器实例
        self._init_playwright()
        
        try:
            # 尝试从池中获取
            browser = self._pool.get(block=False)
            if not self._is_browser_alive(browser):
                logger.warning("浏览器实例已失效，创建新实例")
                browser.close()
                browser = self._create_browser()
            else:
                logger.debug("从池中获取浏览器实例")
            return browser
        except Empty:
            # 池为空，创建新实例
            with self._lock:
                if self._count < self.max_size:
                    self._count += 1
                    logger.info(f"创建新浏览器实例，当前数量: {self._count}")
                    return self._create_browser()
            
            # 等待池中有可用实例
            logger.info("等待可用浏览器实例...")
            return self._pool.get(block=True)
    
    def release(self, browser: Browser):
        # 释放浏览器实例
        if self._is_browser_alive(browser):
            # 清理页面和Cookie
            try:
                for context in browser.contexts:
                    context.clear_cookies()
                    for page in context.pages:
                        page.close()
            except Exception as e:
                logger.warning(f"清理浏览器时出错: {e}")
            
            try:
                self._pool.put(browser, block=False)
                logger.debug("浏览器实例已释放回池中")
            except:
                browser.close()
                with self._lock:
                    self._count -= 1
                logger.info("浏览器池已满，关闭实例")
        else:
            with self._lock:
                self._count -= 1
            logger.warning("释放的浏览器实例已失效")
    
    def _create_browser(self) -> Browser:
        # 创建新浏览器实例
        browser = self._playwright.chromium.launch(
            headless=self.headless,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-web-security',
                '--disable-features=IsolateOrigins,site-per-process',
                '--no-sandbox',
                '--disable-setuid-sandbox'
            ]
        )
        return browser
    
    def _is_browser_alive(self, browser: Browser) -> bool:
        # 检查浏览器是否存活
        try:
            browser.contexts
            return True
        except:
            return False
    
    def close_all(self):
        # 关闭所有浏览器实例
        logger.info("关闭所有浏览器实例...")
        closed = 0
        while not self._pool.empty():
            try:
                browser = self._pool.get(block=False)
                browser.close()
                closed += 1
            except Exception as e:
                logger.error(f"关闭浏览器时出错: {e}")
        
        if self._playwright:
            self._playwright.stop()
            logger.info(f"已关闭 {closed} 个浏览器实例")
