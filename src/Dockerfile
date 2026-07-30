FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy

WORKDIR /app

# 安装依赖
COPY requirements.txt .
RUN pip install -r requirements.txt

# 安装Playwright浏览器
RUN playwright install chromium

# 创建必要目录
RUN mkdir -p logs screenshots documents results

# 复制应用代码
COPY . .

# 设置环境变量
ENV PYTHONUNBUFFERED=1
ENV BROWSER_HEADLESS=true

# 运行应用
CMD ["python", "main.py"]
