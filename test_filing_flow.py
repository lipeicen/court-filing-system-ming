#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
端到端测试：登录一次保存 storage_state，每个案件独立 context，避免页面状态污染。
"""
import os
import sys
import json
import time
from pathlib import Path
from datetime import datetime
from loguru import logger

try:
    import pymysql
except ImportError:
    pymysql = None

DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': 'lijiayu123',
    'database': 'court_filing_civil_test',
    'port': int(os.getenv('DB_PORT', 3306)),
    'charset': 'utf8mb4',
}


def load_config():
    """从 system_config 表加载配置，环境变量优先。"""
    defaults = {
        'BEIJING_COURT_USERNAME': '',
        'BEIJING_COURT_PASSWORD': '',
        'DEFAULT_COURT_NAME': '北京市海淀区人民法院',
        'DEFAULT_COURT_CODE': 'beijing',
        'DEFAULT_CASE_REASON': '买卖合同纠纷',
        'DEFAULT_CASE_TYPE': '民事案件',
        'COURT_BASE_URL': 'https://zxfw.court.gov.cn',
        'DRY_RUN_DEFAULT': 'false',
        'STATE_MAX_AGE_MINUTES': '10',
    }
    if not pymysql:
        return defaults
    try:
        conn = pymysql.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute("SELECT config_key, config_value FROM system_config")
        db_cfg = {row[0]: row[1] or '' for row in cursor.fetchall()}
        conn.close()
    except Exception as e:
        logger.warning(f"读取 system_config 失败，使用默认值: {e}")
        db_cfg = {}
    cfg = defaults.copy()
    cfg.update({k: v for k, v in db_cfg.items() if k in defaults})
    # 环境变量覆盖
    for k in defaults:
        env_val = os.getenv(k)
        if env_val is not None:
            cfg[k] = env_val
    return cfg


SYS_CONFIG = load_config()



base_dir = os.path.dirname(os.path.abspath(__file__))
src_dir = os.path.join(base_dir, 'src')
sys.path.insert(0, src_dir)

from playwright.sync_api import sync_playwright
from adapters import BeijingCourtAdapter
from models import CaseInfo, Party, CaseDocument

DATA_PATH = os.path.join(base_dir, 'test_data', 'test_cases.json')
RESULT_DIR = os.path.join(base_dir, 'results')
LOG_DIR = os.path.join(base_dir, 'logs')
STATE_PATH = os.path.join(base_dir, 'test_data', 'auth_state.json')
for d in (RESULT_DIR, LOG_DIR, os.path.dirname(STATE_PATH)):
    os.makedirs(d, exist_ok=True)

logger.add(
    os.path.join(LOG_DIR, 'test_filing_flow.log'),
    rotation="10 MB",
    retention="7 days",
    level="INFO",
    encoding="utf-8"
)


def load_cases():
    with open(DATA_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_cases_from_db(limit=10):
    """从数据库 cases + case_files 加载待立案案件。先按案件 LIMIT，再查文件，避免 JOIN 展开行截断。"""
    if not pymysql:
        raise ImportError('请安装 pymysql: pip install pymysql')
    conn = pymysql.connect(**DB_CONFIG)
    try:
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        cursor.execute("""
            SELECT * FROM cases
            WHERE status = 0
            ORDER BY id DESC
            LIMIT %s
        """, (limit,))
        case_rows = cursor.fetchall()
        case_ids = [r['id'] for r in case_rows]
        file_rows = []
        if case_ids:
            placeholders = ','.join(['%s'] * len(case_ids))
            cursor.execute(f"""
                SELECT case_id, file_category, file_name, file_path
                FROM case_files
                WHERE case_id IN ({placeholders})
            """, tuple(case_ids))
            file_rows = cursor.fetchall()
    finally:
        conn.close()

    files_map = {}
    for fr in file_rows:
        files_map.setdefault(fr['case_id'], []).append(fr)

    cases_map = {}
    for row in case_rows:
        case_id = row['id']
        cases_map[case_id] = {
            'case_no': row['case_no'] or '',
            'case_name': row['case_name'] or '',
            'case_type': row.get('case_type') or SYS_CONFIG.get('DEFAULT_CASE_TYPE', '民事案件'),
            'court_code': row.get('court_code') or SYS_CONFIG.get('DEFAULT_COURT_CODE', 'beijing'),
            'court_name': row.get('court_name') or SYS_CONFIG.get('DEFAULT_COURT_NAME', '北京市海淀区人民法院'),
            'case_cause': row.get('case_reason') or SYS_CONFIG.get('DEFAULT_CASE_REASON', '买卖合同纠纷'),
            'amount': float(row['amount']) if row.get('amount') else 0.0,
            'claims': row.get('claims') or '',
            'facts': row.get('facts') or '',
            'plaintiff': {
                'name': row.get('applicant_name') or '',
                'idcard': row.get('applicant_id') or row.get('applicant_cert_no') or '',
                'phone': row.get('applicant_phone') or '',
                'address': row.get('applicant_address') or '',
            },
            'defendant': {
                'name': row.get('respondent_name') or '',
                'idcard': row.get('respondent_id') or row.get('respondent_cert_no') or '',
                'phone': row.get('respondent_phone') or '',
                'address': row.get('respondent_address') or '',
            },
            'documents': [],
        }
        for fr in files_map.get(case_id, []):
            if fr.get('file_path'):
                cases_map[case_id]['documents'].append({
                    'name': fr.get('file_name') or fr.get('file_category') or '材料',
                    'type': fr.get('file_category') or '其他材料',
                    'path': fr['file_path'],
                })
    return list(cases_map.values())


def build_case_info(raw):

    parties = [
        Party(
            name=raw['plaintiff']['name'],
            idcard=raw['plaintiff']['idcard'],
            phone=raw['plaintiff']['phone'],
            address=raw['plaintiff']['address'],
            party_type='原告'
        ),
        Party(
            name=raw['defendant']['name'],
            idcard=raw['defendant']['idcard'],
            phone=raw['defendant']['phone'],
            address=raw['defendant']['address'],
            party_type='被告'
        )
    ]
    docs = [
        CaseDocument(
            name=d['name'],
            path=os.path.join(base_dir, d['path']),
            doc_type=d['type'],
            description=d['name']
        )
        for d in raw['documents']
    ]
    return CaseInfo(
        case_type=raw['case_type'],
        court_code=raw['court_code'],
        court_name=raw['court_name'],
        parties=parties,
        claims=raw['claims'],
        facts=raw['facts'],
        amount=raw['amount'],
        documents=docs,
        metadata={
            'case_no': raw['case_no'],
            'case_cause': raw.get('case_cause', '买卖合同纠纷')
        }
    )


def save_report(report, suffix=''):
    report_path = os.path.join(RESULT_DIR, f'test_filing_report_{datetime.now().strftime("%Y%m%d_%H%M%S")}{suffix}.json')
    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    logger.info(f"测试报告: {report_path}")
    return report_path


def _validate_state() -> bool:
    """打开首页验证 storage_state 是否仍有效，且文件保存时间在 5 分钟内"""
    if not Path(STATE_PATH).exists():
        return False
    # 服务端登录态容易过期，超过 5 分钟强制刷新
    max_age = int(SYS_CONFIG.get('STATE_MAX_AGE_MINUTES', '10')) * 60
    if time.time() - Path(STATE_PATH).stat().st_mtime > max_age:
        logger.warning(f"storage_state 超过 {SYS_CONFIG.get('STATE_MAX_AGE_MINUTES', '10')} 分钟，强制重新登录")
        return False
    adapter = BeijingCourtAdapter()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(storage_state=STATE_PATH, viewport={'width': 1920, 'height': 1080})
        page = context.new_page()
        try:
            page.goto(f"{adapter.base_url}/zxfw/#/pages/pc/home/index", wait_until="domcontentloaded", timeout=10000)
            adapter._wait(2)
            content = page.content()
            valid = "在线立案" in content and "密码登录" not in content
            if not valid:
                logger.warning(f"storage_state 已失效，需要重新登录")
            return valid
        except Exception as e:
            logger.warning(f"验证登录态失败: {e}")
            return False
        finally:
            context.close()
            browser.close()


def prepare_login_state():
    """登录态有效则复用，否则重新登录（headless=False 提高验证码成功率）"""
    if _validate_state():
        logger.info(f"登录态有效，跳过重新登录: {STATE_PATH}")
        return
    adapter = BeijingCourtAdapter()
    credentials = {
        'username': SYS_CONFIG.get('BEIJING_COURT_USERNAME', ''),
        'password': SYS_CONFIG.get('BEIJING_COURT_PASSWORD', '')
    }
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(viewport={'width': 1920, 'height': 1080})
        page = context.new_page()
        if not adapter.login(page, credentials):
            raise Exception('登录失败')
        context.storage_state(path=STATE_PATH)
        browser.close()
    logger.info(f"登录态已保存: {STATE_PATH}")


def run_case(browser, raw, index):
    case_info = build_case_info(raw)
    case_no = case_info.metadata['case_no']
    logger.info(f"--- [{index}] 测试案件 {case_no} ---")

    res = {
        'case_no': case_no,
        'status': '未知',
        'message': '',
        'case_id': None,
        'steps': []
    }

    adapter = BeijingCourtAdapter()
    context = browser.new_context(storage_state=STATE_PATH, viewport={'width': 1920, 'height': 1080})
    page = context.new_page()
    try:
        # 先回到首页，再导航立案
        page.goto('https://zxfw.court.gov.cn/zxfw/#/pages/index/index', wait_until='domcontentloaded')
        time.sleep(2)
        popup = adapter.navigate_to_filing(page)
        if not popup:
            raise Exception('未能进入立案表单页面')
        adapter.fill_case_form(popup, case_info.to_dict())
        if case_info.documents:
            adapter.upload_documents(popup, [d.to_dict() for d in case_info.documents])
        # 填写当事人信息并提交
        adapter.fill_party_form(popup, case_info.to_dict())
        adapter.complete_case_info_and_preview(popup, case_info.to_dict())
        dry_run = os.getenv('COURT_FILING_DRY_RUN', SYS_CONFIG.get('DRY_RUN_DEFAULT', 'false')).lower() in ('true', '1', 'yes')
        submit = adapter.submit_case(popup, case_info.to_dict(), dry_run=dry_run)
        if dry_run:
            res['status'] = submit.get('success') and '待提交' or '已驳回'
        else:
            res['status'] = submit.get('success') and '已提交' or '已驳回'
        res['message'] = submit.get('message', '')
        res['case_id'] = submit.get('case_id')
        logger.info(f"结果: {res['status']} | {res['message']}")
    except Exception as e:
        logger.exception(f"案件 {case_no} 异常")
        res['status'] = '异常'
        res['message'] = str(e)
    finally:
        try:
            context.storage_state(path=STATE_PATH)
            logger.info(f"已保存当前会话状态: {STATE_PATH}")
        except Exception as e:
            logger.warning(f"保存会话状态失败: {e}")
        context.close()
    return res


def run_all_cases():
    raw_cases = load_cases()
    logger.info(f"加载 {len(raw_cases)} 个测试案件")

    report = {
        'time': datetime.now().isoformat(),
        'total': len(raw_cases),
        'results': []
    }

    prepare_login_state()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        for i, raw in enumerate(raw_cases, 1):
            res = run_case(browser, raw, i)
            report['results'].append(res)
            save_report(report, suffix=f'_progress_{i}of{len(raw_cases)}')
            time.sleep(2)
        browser.close()

    save_report(report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return report


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--case-idx', type=int, default=-1, help='只跑指定索引的案件（0-based），-1 跑全部')
    parser.add_argument('--headless', type=lambda x: x.lower() in ('true', '1', 'yes'), default=True)
    parser.add_argument('--from-db', action='store_true', help='从数据库 cases/case_files 加载案件和材料')
    parser.add_argument('--db-limit', type=int, default=10, help='从数据库加载的案件数量上限')
    args = parser.parse_args()

    raw_cases = load_cases_from_db(args.db_limit) if args.from_db else load_cases()
    if args.case_idx >= 0:
        raw_cases = [raw_cases[args.case_idx]]

    report = {
        'time': __import__('datetime').datetime.now().isoformat(),
        'total': len(raw_cases),
        'results': []
    }
    prepare_login_state()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=args.headless)
        for i, raw in enumerate(raw_cases, 1):
            res = run_case(browser, raw, i)
            report['results'].append(res)
            save_report(report, suffix=f'_progress_{i}of{len(raw_cases)}')
            time.sleep(2)
        browser.close()

    save_report(report)
    print(json.dumps(report, ensure_ascii=False, indent=2))

