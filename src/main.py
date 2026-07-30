import os
import sys
import json
from loguru import logger
from workflow import FilingWorkflow
from models import CaseInfo, Party, CaseDocument, FilingStatus
from config import settings

os.makedirs("logs", exist_ok=True)
os.makedirs("screenshots", exist_ok=True)
os.makedirs("documents", exist_ok=True)

logger.add(
    "logs/filing.log",
    rotation="10 MB",
    retention="30 days",
    level=settings.LOG_LEVEL,
    encoding="utf-8"
)

def create_sample_case() -> CaseInfo:
    plaintiff = Party(
        name="张三",
        idcard="110101199001011234",
        phone="13800138000",
        address="北京市朝阳区xxx街道xxx号",
        party_type="原告"
    )
    defendant = Party(
        name="李四",
        idcard="110101199002021234",
        phone="13900139000",
        address="北京市海淀区xxx街道xxx号",
        party_type="被告"
    )
    documents = [
        CaseDocument(name="起诉状", path="documents/起诉状.pdf", doc_type="起诉状", description="民事起诉状"),
        CaseDocument(name="身份证明", path="documents/身份证.pdf", doc_type="身份证明", description="原告身份证复印件"),
        CaseDocument(name="证据材料", path="documents/证据.pdf", doc_type="证据", description="相关证据材料"),
    ]
    return CaseInfo(
        case_type="民事案件",
        court_code="beijing",
        court_name="北京市朝阳区人民法院",
        parties=[plaintiff, defendant],
        claims="请求判令被告支付欠款人民币10万元及利息",
        facts="2023年1月，被告向原告借款10万元，约定2023年12月归还。到期后被告未归还，经多次催讨未果。",
        amount=100000.00,
        documents=documents,
        metadata={"urgent": False, "category": "借贷纠纷"}
    )

def main():
    logger.info("=== 法院自动立案系统启动 ===")
    workflow = FilingWorkflow(headless=settings.BROWSER_HEADLESS)
    try:
        case = create_sample_case()
        logger.info(f"案件信息: {case.to_dict()}")
        logger.info("开始执行立案流程...")
        result = workflow.execute(case)
        print("\n" + "="*50)
        print("立案结果")
        print("="*50)
        print(f"状态: {result.status.value}")
        print(f"案号: {result.case_id or '无'}")
        print(f"消息: {result.message}")
        print(f"法院: {result.court_name}")
        print(f"步骤数: {len(result.steps)}")
        print("="*50)
        os.makedirs("results", exist_ok=True)
        result_file = f"results/result_{result.created_at.replace(':', '-').replace('.', '_')}.json"
        with open(result_file, "w", encoding="utf-8") as f:
            json.dump(result.to_dict(), f, ensure_ascii=False, indent=2)
        logger.info(f"结果已保存: {result_file}")
    except KeyboardInterrupt:
        logger.info("用户中断操作")
    except Exception as e:
        logger.error(f"程序出错: {e}")
        raise
    finally:
        workflow.close()
        logger.info("=== 系统已关闭 ===")

if __name__ == "__main__":
    main()
