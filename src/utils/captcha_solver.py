import base64
import random
from io import BytesIO
from PIL import Image
import requests
from loguru import logger
from config import settings

class CaptchaSolver:
    # 验证码处理器
    
    def __init__(self, api_key: str = None):
        self.api_key = api_key or settings.CAPTCHA_API_KEY
        self.api_url = settings.CAPTCHA_API_URL
    
    def solve_image_captcha(self, image_bytes: bytes) -> str:
        # 识别图片验证码
        logger.info("识别图片验证码...")
        
        try:
            # 使用本地ddddocr识别
            import ddddocr
            ocr = ddddocr.DdddOcr(show_ad=False)
            text = ocr.classification(image_bytes)
            logger.info(f"验证码识别结果: {text}")
            return text
        except Exception as e:
            logger.error(f"本地OCR识别失败: {e}")
            # 回退到API方式
            try:
                processed_image = self._preprocess_image(image_bytes)
                result = self._call_api(processed_image, captcha_type="image")
                text = result.get("text", "")
                logger.info(f"API识别结果: {text}")
                return text
            except Exception as e2:
                logger.error(f"API识别也失败: {e2}")
                return ""
    
    def solve_slider_captcha(self, page, slider_selector: str) -> bool:
        # 处理滑块验证码
        logger.info("处理滑块验证码...")
        
        try:
            slider = page.locator(slider_selector)
            track = page.locator(".slider-track")
            
            # 获取滑块和轨道位置
            slider_box = slider.bounding_box()
            track_box = track.bounding_box()
            
            if not slider_box or not track_box:
                logger.error("无法获取滑块或轨道位置")
                return False
            
            # 计算滑动距离
            distance = track_box["width"] - slider_box["width"]
            
            # 模拟人类滑动轨迹
            trajectory = self._generate_trajectory(distance)
            
            # 执行滑动
            start_x = slider_box["x"] + slider_box["width"] / 2
            start_y = slider_box["y"] + slider_box["height"] / 2
            
            page.mouse.move(start_x, start_y)
            page.mouse.down()
            
            for x in trajectory:
                page.mouse.move(slider_box["x"] + x, start_y)
                page.wait_for_timeout(random.randint(10, 20))
            
            page.mouse.up()
            
            # 验证是否通过
            page.wait_for_timeout(500)
            success = not page.is_visible(slider_selector)
            logger.info(f"滑块验证结果: {success}")
            return success
            
        except Exception as e:
            logger.error(f"滑块验证失败: {e}")
            return False
    
    def solve_click_captcha(self, page, instruction: str) -> bool:
        # 处理点击验证码(如点击特定文字)
        logger.info(f"处理点击验证码: {instruction}")
        
        try:
            # 使用AI模型识别需要点击的位置
            screenshot = page.screenshot()
            click_points = self._ai_detect_click_points(screenshot, instruction)
            
            for point in click_points:
                page.mouse.click(point["x"], point["y"])
                page.wait_for_timeout(500)
            
            return True
        except Exception as e:
            logger.error(f"点击验证码处理失败: {e}")
            return False
    
    def _preprocess_image(self, image_bytes: bytes) -> bytes:
        # 预处理图片 - 提高识别率
        image = Image.open(BytesIO(image_bytes))
        
        # 转换为灰度图
        image = image.convert("L")
        
        # 二值化
        threshold = 128
        image = image.point(lambda x: 0 if x < threshold else 255, "1")
        
        # 保存为bytes
        output = BytesIO()
        image.save(output, format="PNG")
        return output.getvalue()
    
    def _generate_trajectory(self, distance: int) -> list:
        # 生成人类-like滑动轨迹
        trajectory = []
        current = 0
        
        # 先加速后减速
        while current < distance:
            if current < distance * 0.6:
                step = random.randint(3, 8)
            else:
                step = random.randint(1, 4)
            
            current += step
            trajectory.append(min(current, distance))
        
        # 添加回退效果
        if random.random() > 0.5:
            back_steps = random.randint(1, 3)
            for _ in range(back_steps):
                if trajectory:
                    trajectory.append(trajectory[-1] - random.randint(1, 3))
            trajectory.append(distance)
        
        return trajectory
    
    def _call_api(self, image_bytes: bytes, captcha_type: str) -> dict:
        # 调用打码平台API
        if not self.api_key:
            raise ValueError("未配置验证码API密钥")
        
        response = requests.post(
            self.api_url,
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "image": base64.b64encode(image_bytes).decode(),
                "type": captcha_type
            },
            timeout=30
        )
        
        response.raise_for_status()
        return response.json()
    
    def _ai_detect_click_points(self, screenshot: bytes, instruction: str) -> list:
        # AI识别点击位置 (简化版)
        # 实际项目中需要集成OCR或目标检测模型
        logger.warning("AI点击点检测需要集成OCR模型")
        return []
