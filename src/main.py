import os
import sys
import json
from loguru import logger
from workflow import FilingWorkflow
from models import CaseInfo, Party, CaseDocument, FilingStatus
from config import settings
import pymysql

os.makedirs("logs", exist_ok=True)
os.makedirs("screenshots", exist_ok=True)
os.makedirs("documents", exist_ok=True)
os.makedirs("results", exist_ok=True)

logger.add(
    "logs/filing.log",
    rotation="10 MB",
    retention="30 days",
    level=settings.LOG_LEVEL,
    encoding="utf-8"
)

DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "lijiayu123",
    "database": "court_filing_civil",
    "charset": "utf8mb4",
}

# 数据库 file_category 到 workflow 中 CaseDocument.doc_type 的映射
DOC_CATEGORY_MAP = {
    "起诉状": ["起诉状", "起诉材料"],
    "身份证明": ["身份证明", "当事人身份证明"],
    "证据": ["证据", "证据目录及证据材料"],
    "委托书": ["委托", "代理人委托手续和身份材料", "授权"],
    "送达地址确认书": ["送达"],
    "其他材料": ["其他"],
}


def map_doc_category(file_category: str) -> str:
    for canonical, kws in DOC_CATEGORY_MAP.items():
        if any(k in (file_category or "") for k in kws):
            return canonical
    return "其他材料"


def load_pending_cases(limit=None):
    """从数据库读取待立案案件"""
    conn = pymysql.connect(**DB_CONFIG)
    cursor = conn.cursor()
    where = "WHERE (filing_status IS NULL OR filing_status = '') AND (status = 0 OR status IS NULL)"
    cursor.execute(f"SELECT id FROM cases {where} ORDER BY id LIMIT {limit if limit is not None else 999}")
    ids = [r[0] for r in cursor.fetchall()]
    cases = []
    for cid in ids:
        cursor.execute("""
            SELECT id, case_no, case_name, case_type, case_reason, court_name, court_code,
                   claim_amount, claim, facts, delivery_address, contact_name, contact_phone,
                   applicant_type, applicant_name, applicant_id, applicant_phone, applicant_address,
                   applicant_cert_type, applicant_gender, applicant_nation, applicant_email, applicant_occupation,
                   respondent_type, respondent_name, respondent_id, respondent_phone, respondent_address,
                   respondent_cert_type, respondent_gender, respondent_nation, respondent_email, respondent_occupation,
                   has_agent, agent_type, agent_name, agent_id, agent_phone, agent_law_firm
            FROM cases WHERE id=%s
        """, (cid,))
        row = cursor.fetchone()
        if not row:
            continue
        (id, case_no, case_name, case_type, case_reason, court_name, court_code,
         claim_amount, claim, facts, delivery_address, contact_name, contact_phone,
         applicant_type, applicant_name, applicant_id, applicant_phone, applicant_address,
         applicant_cert_type, applicant_gender, applicant_nation, applicant_email, applicant_occupation,
         respondent_type, respondent_name, respondent_id, respondent_phone, respondent_address,
         respondent_cert_type, respondent_gender, respondent_nation, respondent_email, respondent_occupation,
         has_agent, agent_type, agent_name, agent_id, agent_phone, agent_law_firm) = row

        cursor.execute("SELECT file_category, file_name, file_path FROM case_files WHERE case_id=%s", (cid,))
        files = cursor.fetchall()
        cases.append({
            'id': id, 'case_no': case_no, 'case_name': case_name, 'case_type': case_type or '民事案件',
            'case_reason': case_reason, 'court_name': court_name, 'court_code': court_code or 'beijing',
            'claim_amount': float(claim_amount) if claim_amount else 0,
            'claims': claim, 'facts': facts, 'delivery_address': delivery_address,
            'contact_name': contact_name, 'contact_phone': contact_phone,
            'applicant_type': applicant_type, 'applicant_name': applicant_name, 'applicant_id': applicant_id,
            'applicant_phone': applicant_phone, 'applicant_address': applicant_address,
            'applicant_cert_type': applicant_cert_type, 'applicant_gender': applicant_gender, 'applicant_nation': applicant_nation,
            'applicant_email': applicant_email, 'applicant_occupation': applicant_occupation,
            'respondent_type': respondent_type, 'respondent_name': respondent_name, 'respondent_id': respondent_id,
            'respondent_phone': respondent_phone, 'respondent_address': respondent_address,
            'respondent_cert_type': respondent_cert_type, 'respondent_gender': respondent_gender, 'respondent_nation': respondent_nation,
            'respondent_email': respondent_email, 'respondent_occupation': respondent_occupation,
            'has_agent': bool(has_agent), 'agent_type': agent_type, 'agent_name': agent_name,
            'agent_id': agent_id, 'agent_phone': agent_phone, 'agent_law_firm': agent_law_firm,
            'files': [(cat, name, path) for cat, name, path in files]
        })
    conn.close()
    return cases


def case_to_case_info(case_row: dict) -> CaseInfo:
    """将数据库案件行转换为 CaseInfo 对象"""
    docs = []
    for cat, name, path in case_row['files']:
        if not os.path.exists(path):
            logger.warning(f"案件 {case_row['case_no']} 文件缺失: {path}")
            continue
        canonical = map_doc_category(cat)
        docs.append(CaseDocument(
            name=name or canonical,
            path=path,
            doc_type=canonical,
            description=cat
        ))

    a = case_row
    parties = [
        Party(
            name=a['applicant_name'] or '原告',
            idcard=a['applicant_id'] or '',
            phone=a['applicant_phone'] or '',
            address=a['applicant_address'] or a['delivery_address'] or '',
            party_type='原告',
            cert_no=a['applicant_id'] or '',
            cert_type=a['applicant_cert_type'] or '居民身份证',
            party_category=a['applicant_type'] or '自然人',
            gender=a['applicant_gender'] or '男',
            nation=a['applicant_nation'] or '汉族'
        ),
        Party(
            name=a['respondent_name'] or '被告',
            idcard=a['respondent_id'] or '',
            phone=a['respondent_phone'] or '',
            address=a['respondent_address'] or '',
            party_type='被告',
            cert_no=a['respondent_id'] or '',
            cert_type=a['respondent_cert_type'] or '居民身份证',
            party_category=a['respondent_type'] or '自然人',
            gender=a['respondent_gender'] or '男',
            nation=a['respondent_nation'] or '汉族'
        ),
    ]

    if a['has_agent'] and a['agent_name']:
        parties.append(Party(
            name=a['agent_name'],
            idcard=a['agent_id'] or '',
            phone=a['agent_phone'] or '',
            address='',
            party_type='代理人',
            cert_no=a['agent_id'] or '',
            cert_type='居民身份证',
            party_category='律师' if '律师' in (a['agent_type'] or '') else (a['agent_type'] or '律师'),
            gender='男',
            nation='汉族'
        ))

    court_code = a['court_code']
    if not court_code:
        court_code = 'beijing' if '北京' in (a['court_name'] or '') else 'default'

    return CaseInfo(
        case_type=a['case_type'],
        court_code=court_code,
        court_name=a['court_name'] or '',
        parties=parties,
        claims=a['claims'] or '',
        facts=a['facts'] or '',
        claim_amount=a['claim_amount'],
        documents=docs,
        metadata={
            'case_no': a['case_no'],
            'case_id': a['id'],
            'case_reason': a['case_reason'],
            'contact_name': a['contact_name'],
            'contact_phone': a['contact_phone']
        }
    )


def update_case_status(case_id: int, status: str, success: bool):
    """立案完成后更新数据库状态"""
    conn = pymysql.connect(**DB_CONFIG)
    cursor = conn.cursor()
    try:
        cursor.execute(
            "UPDATE cases SET filing_status=%s, status=%s, updated_at=NOW() WHERE id=%s",
            (status, 1 if success else 0, case_id)
        )
        conn.commit()
    except Exception as e:
        logger.error(f"更新数据库状态失败: {e}")
    finally:
        conn.close()


def main():
    logger.info("=== 法院自动立案系统启动 ===")
    workflow = FilingWorkflow(headless=settings.BROWSER_HEADLESS)
    try:
        pending = load_pending_cases(limit=1)
        if not pending:
            logger.info("没有待立案的案件")
            return

        supported_courts = set(workflow.adapter_factory.list_supported_courts())
        for case_row in pending:
            if case_row['court_code'] not in supported_courts:
                logger.warning(f"跳过不支持的法院代码: {case_row['court_code']} ({case_row['court_name']})")
                continue
            case_info = case_to_case_info(case_row)
            logger.info(f"处理案件: {case_row['case_no']} -> {case_row['court_name']}")
            logger.info(f"案件信息: {case_info.to_dict()}")
            logger.info("开始执行立案流程...")
            result = workflow.execute(case_info)

            print("\n" + "=" * 50)
            print("立案结果")
            print("=" * 50)
            print(f"案件编号: {case_row['case_no']}")
            print(f"状态: {result.status.value}")
            print(f"案号: {result.case_id or '无'}")
            print(f"消息: {result.message}")
            print(f"法院: {result.court_name}")
            print(f"步骤数: {len(result.steps)}")
            print("=" * 50)

            success = result.status == FilingStatus.SUBMITTED
            update_case_status(case_row['id'], result.message, success)

            result_file = f"results/result_{case_row['case_no'].replace('/', '_')}_{result.created_at.replace(':', '-').replace('.', '_')}.json"
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
