# 法院自动立案系统

基于 Playwright 的法院网站自动化立案工具。

## 功能特性

- 多法院适配器支持（北京、上海、广东、浙江等）
- 智能验证码处理（图片/滑块/点击）
- 浏览器连接池管理
- 反检测策略（指纹伪装、请求拦截）
- 操作录制与截图
- 完整的日志记录

## 安装

```bash
# 安装依赖
pip install -r requirements.txt

# 安装Playwright浏览器
playwright install chromium
```

## 配置

1. 复制环境变量文件
```bash
cp .env.example .env
```

2. 编辑 `.env` 文件，配置法院账号和验证码API密钥

## 使用

### 运行示例

```bash
python main.py
```

### 自定义案件

```python
from workflow import FilingWorkflow
from models import CaseInfo, Party, CaseDocument

# 创建案件
case = CaseInfo(
    case_type="民事案件",
    court_code="beijing",
    parties=[
        Party(name="张三", idcard="...", phone="...", party_type="原告")
    ],
    claims="诉讼请求...",
    facts="事实与理由...",
    amount=100000.00,
    documents=[
        CaseDocument(name="起诉状", path="documents/起诉状.pdf", doc_type="起诉状")
    ]
)

# 执行立案
workflow = FilingWorkflow()
result = workflow.execute(case)
print(result)
```

## 项目结构

```
src/
├── adapters/          # 法院适配器
│   ├── base.py       # 适配器基类
│   └── beijing_court.py  # 北京法院适配器
├── core/             # 核心功能
│   ├── browser_pool.py   # 浏览器池
│   ├── stealth.py       # 反检测
│   └── smart_wait.py    # 智能等待
├── utils/            # 工具类
│   ├── captcha_solver.py    # 验证码处理
│   ├── document_uploader.py # 文件上传
│   └── operation_recorder.py # 操作录制
├── config/           # 配置
│   └── settings.py   # 设置
├── models.py         # 数据模型
├── workflow.py       # 工作流
└── main.py          # 入口
```

## 注意事项

1. 请确保已安装 Chrome 浏览器
2. 法院账号需要提前注册并完成实名认证
3. 验证码API需要自行申请
4. 请勿频繁操作，避免账号被封禁

## License

MIT
