from abc import ABC, abstractmethod
from loguru import logger

class CourtAdapter(ABC):
    # 法院网站适配器基类
    
    @property
    @abstractmethod
    def court_name(self) -> str:
        # 法院名称
        pass
    
    @property
    @abstractmethod
    def court_code(self) -> str:
        # 法院代码
        pass
    
    @property
    @abstractmethod
    def base_url(self) -> str:
        # 法院网站基础URL
        pass
    
    @abstractmethod
    def login(self, page, credentials: dict) -> bool:
        # 登录系统
        pass
    
    @abstractmethod
    def navigate_to_filing(self, page) -> None:
        # 导航到立案页面
        pass
    
    @abstractmethod
    def fill_case_form(self, page, case_data: dict) -> None:
        # 填写案件信息
        pass
    
    @abstractmethod
    def upload_documents(self, page, documents: list) -> None:
        # 上传案件材料
        pass
    
    @abstractmethod
    def submit_case(self, page) -> dict:
        # 提交立案申请
        pass
    
    @abstractmethod
    def check_status(self, page, case_id: str) -> dict:
        # 查询案件状态
        pass
    
    def _solve_captcha(self, captcha_solver, image_bytes: bytes) -> str:
        # 调用验证码识别
        if not image_bytes:
            return ""
        return captcha_solver.solve_image_captcha(image_bytes)
    
    def _log_step(self, step_name: str):
        # 记录步骤
        logger.info(f"[{self.court_name}] {step_name}")
