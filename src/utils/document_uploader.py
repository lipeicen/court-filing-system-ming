import os
from pathlib import Path
from loguru import logger

class DocumentUploader:
    # 文件上传处理器
    
    def __init__(self, page):
        self.page = page
    
    def upload_file(self, file_path: str, file_type: str = "auto") -> bool:
        # 上传单个文件
        logger.info(f"上传文件: {file_path}, 类型: {file_type}")
        
        # 检查文件是否存在
        if not os.path.exists(file_path):
            logger.error(f"文件不存在: {file_path}")
            return False
        
        # 查找对应类型的上传控件
        upload_input = self._find_upload_input(file_type)
        
        if not upload_input:
            logger.error(f"未找到类型为 {file_type} 的上传控件")
            return False
        
        try:
            # 设置文件
            upload_input.set_input_files(file_path)
            
            # 等待上传完成
            success = self._wait_upload_complete(file_path)
            if success:
                logger.info(f"文件上传成功: {os.path.basename(file_path)}")
            else:
                logger.warning(f"文件上传超时: {os.path.basename(file_path)}")
            return success
            
        except Exception as e:
            logger.error(f"文件上传失败: {e}")
            return False
    
    def upload_multiple(self, files: list) -> dict:
        # 批量上传文件
        results = {}
        
        for file_info in files:
            try:
                success = self.upload_file(
                    file_info["path"], 
                    file_info.get("type", "auto")
                )
                results[file_info["name"]] = {
                    "success": success,
                    "message": "上传成功" if success else "上传失败"
                }
            except Exception as e:
                results[file_info["name"]] = {
                    "success": False,
                    "message": str(e)
                }
        
        return results
    
    def _find_upload_input(self, file_type: str):
        # 查找上传控件
        # 尝试多种定位策略
        selectors = [
            f"input[type='file'][data-type='{file_type}']",
            f"input[type='file'][accept*='{file_type}']",
            f".upload-area[data-doc-type='{file_type}'] input[type='file']",
            "input[type='file']"
        ]
        
        for selector in selectors:
            try:
                element = self.page.locator(selector).first
                if element.is_visible():
                    logger.debug(f"找到上传控件: {selector}")
                    return element
            except:
                continue
        
        return None
    
    def _wait_upload_complete(self, file_path: str, timeout: int = 30000) -> bool:
        # 等待上传完成
        file_name = os.path.basename(file_path)
        
        try:
            # 等待文件名出现在页面上
            self.page.wait_for_selector(
                f"text={file_name}", 
                state="visible", 
                timeout=timeout
            )
            return True
        except:
            # 尝试检查上传进度
            try:
                self.page.wait_for_selector(
                    ".upload-success, .file-list .item",
                    state="visible",
                    timeout=timeout
                )
                return True
            except:
                return False
