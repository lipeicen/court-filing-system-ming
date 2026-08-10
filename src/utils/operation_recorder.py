import os
from datetime import datetime
from loguru import logger
from config import settings

class OperationRecorder:
    # 操作录制器
    
    def __init__(self, page):
        self.page = page
        self.operations = []
        self._setup_listeners()
        
        # 确保截图目录存在
        os.makedirs(settings.SCREENSHOT_DIR, exist_ok=True)
    
    def set_page(self, page):
        """切换绑定的页面（例如从主页面切到弹窗页面）"""
        self.page = page
        self._setup_listeners()
    
    def _setup_listeners(self):
        # 设置事件监听
        self.page.on("console", self._on_console)
        self.page.on("pageerror", self._on_error)
        self.page.on("request", self._on_request)
        self.page.on("response", self._on_response)
    
    def _on_console(self, msg):
        # 记录控制台输出
        self.operations.append({
            "type": "console",
            "level": msg.type,
            "text": msg.text,
            "time": datetime.now().isoformat()
        })
    
    def _on_error(self, error):
        # 记录页面错误
        self.operations.append({
            "type": "error",
            "message": getattr(error, 'message', str(error)),
            "stack": getattr(error, 'stack', ''),
            "time": datetime.now().isoformat()
        })
        logger.error(f"页面错误: {getattr(error, 'message', str(error))}")
    
    def _on_request(self, request):
        # 记录请求
        self.operations.append({
            "type": "request",
            "url": request.url,
            "method": request.method,
            "time": datetime.now().isoformat()
        })
    
    def _on_response(self, response):
        # 记录响应
        self.operations.append({
            "type": "response",
            "url": response.url,
            "status": response.status,
            "time": datetime.now().isoformat()
        })
    
    def save_screenshot(self, name: str = None):
        # 保存截图
        if name is None:
            name = f"screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        path = os.path.join(settings.SCREENSHOT_DIR, f"{name}.png")
        
        try:
            self.page.screenshot(path=path, full_page=False, timeout=5000)
            self.operations.append({
                "type": "screenshot",
                "path": path,
                "time": datetime.now().isoformat()
            })
            logger.info(f"截图已保存: {path}")
            return path
        except Exception as e:
            logger.error(f"截图保存失败: {e}")
            return None
    
    def get_report(self) -> dict:
        # 生成操作报告
        errors = [op for op in self.operations if op["type"] == "error"]
        requests_count = len([op for op in self.operations if op["type"] == "request"])
        
        return {
            "total_operations": len(self.operations),
            "errors_count": len(errors),
            "errors": errors,
            "requests_count": requests_count,
            "timeline": self.operations
        }
