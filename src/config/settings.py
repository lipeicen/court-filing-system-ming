import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    # 浏览器配置
    BROWSER_HEADLESS = os.getenv('BROWSER_HEADLESS', 'true').lower() == 'true'
    BROWSER_POOL_SIZE = int(os.getenv('BROWSER_POOL_SIZE', '5'))
    BROWSER_TIMEOUT = int(os.getenv('BROWSER_TIMEOUT', '30000'))
    
    # 验证码配置
    CAPTCHA_API_KEY = os.getenv('CAPTCHA_API_KEY', '')
    CAPTCHA_API_URL = os.getenv('CAPTCHA_API_URL', 'https://api.captcha-service.com/solve')
    
    # 法院账号配置
    COURT_CREDENTIALS = {
        'beijing': {
            'username': os.getenv('BEIJING_COURT_USERNAME', ''),
            'password': os.getenv('BEIJING_COURT_PASSWORD', '')
        },
        'shanghai': {
            'username': os.getenv('SHANGHAI_COURT_USERNAME', ''),
            'password': os.getenv('SHANGHAI_COURT_PASSWORD', '')
        }
    }
    
    # 日志配置
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
    LOG_FILE = os.getenv('LOG_FILE', 'logs/filing.log')
    
    # 截图配置
    SCREENSHOT_DIR = os.getenv('SCREENSHOT_DIR', 'screenshots')
    
    # 文档配置
    DOCUMENT_DIR = os.getenv('DOCUMENT_DIR', 'documents')

settings = Settings()
