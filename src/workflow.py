from datetime import datetime
from loguru import logger
from core import BrowserPool, StealthConfig
from adapters import CourtAdapter, BeijingCourtAdapter
from models import CaseInfo, FilingResult, FilingStatus
from utils import CaptchaSolver, OperationRecorder
from config import settings

class CourtAdapterFactory:
    # 法院适配器工厂
    
    _adapters = {
        "beijing": BeijingCourtAdapter,
    }
    
    @classmethod
    def get_adapter(cls, court_code: str) -> CourtAdapter:
        adapter_class = cls._adapters.get(court_code)
        if not adapter_class:
            raise ValueError(f"不支持的法院代码: {court_code}")
        return adapter_class()
    
    @classmethod
    def register_adapter(cls, court_code: str, adapter_class: type):
        cls._adapters[court_code] = adapter_class
    
    @classmethod
    def list_supported_courts(cls) -> list:
        return list(cls._adapters.keys())

class FilingWorkflow:
    # 立案工作流
    
    def __init__(self, browser_pool: BrowserPool = None, headless: bool = None):
        self.browser_pool = browser_pool or BrowserPool(headless=headless)
        self.adapter_factory = CourtAdapterFactory()
        self.captcha_solver = CaptchaSolver()
        logger.info("立案工作流已初始化")
    
    def execute(self, case_info: CaseInfo, credentials: dict = None) -> FilingResult:
        result = FilingResult(
            status=FilingStatus.PENDING,
            court_code=case_info.court_code
        )
        
        browser = None
        page = None
        popup = None
        recorder = None
        
        try:
            self._log_step(result, "获取浏览器实例")
            browser = self.browser_pool.acquire()
            page = browser.new_page()
            
            StealthConfig.apply(page)
            StealthConfig.setup_route_interception(page)
            
            recorder = OperationRecorder(page)
            
            self._log_step(result, f"加载法院适配器: {case_info.court_code}")
            adapter = self.adapter_factory.get_adapter(case_info.court_code)
            result.court_name = adapter.court_name
            
            if credentials is None:
                credentials = settings.COURT_CREDENTIALS.get(case_info.court_code, {})
            
            self._log_step(result, "登录系统")
            if not adapter.login(page, credentials):
                raise Exception("登录失败，请检查账号密码")
            recorder.save_screenshot("login_success")
            
            self._log_step(result, "导航到民事一审立案页面")
            popup = adapter.navigate_to_filing(page)
            if popup is None:
                raise Exception("未能进入立案表单页面")
            # 后续操作都在 popup 页面，recorder 切换到 popup
            recorder.set_page(popup)
            recorder.save_screenshot("filing_page")
            
            self._log_step(result, "填写案件信息")
            adapter.fill_case_form(popup, case_info.to_dict())
            recorder.save_screenshot("form_filled")
            
            if case_info.documents:
                self._log_step(result, "上传案件材料")
                adapter.upload_documents(popup, [d.to_dict() for d in case_info.documents])
                recorder.save_screenshot("documents_uploaded")
            
            self._log_step(result, "提交立案申请")
            submit_result = adapter.submit_case(popup, case_info.to_dict())
            recorder.save_screenshot("submitted")
            
            result.case_id = submit_result.get("case_id")
            result.status = FilingStatus.SUBMITTED if submit_result["success"] else FilingStatus.REJECTED
            result.message = submit_result.get("message", "")
            
            if submit_result["success"]:
                logger.info(f"立案成功，案号: {result.case_id}")
            else:
                logger.warning(f"立案失败: {result.message}")
            
        except Exception as e:
            logger.error(f"立案流程出错: {e}")
            result.status = FilingStatus.REJECTED
            result.message = str(e)
            if page:
                try:
                    page.screenshot(path="screenshots/error.png")
                except:
                    pass
        
        finally:
            if recorder:
                report = recorder.get_report()
                logger.info(f"操作统计: 总操作 {report['total_operations']}, 错误 {report['errors_count']}")
            if browser:
                self.browser_pool.release(browser)
        
        return result
    
    def check_status(self, case_id: str, court_code: str, credentials: dict = None) -> dict:
        return {"error": "未实现"}
    
    def _log_step(self, result: FilingResult, step_name: str):
        result.steps.append({
            "name": step_name,
            "time": datetime.now().isoformat(),
            "status": "running"
        })
        logger.info(step_name)
    
    def close(self):
        logger.info("关闭立案工作流...")
        self.browser_pool.close_all()
