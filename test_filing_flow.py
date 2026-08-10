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
    if time.time() - Path(STATE_PATH).stat().st_mtime > 10 * 60:
        logger.warning(f"storage_state 超过 5 分钟，强制重新登录")
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
        'username': os.getenv('BEIJING_COURT_USERNAME', ''),
        'password': os.getenv('BEIJING_COURT_PASSWORD', '')
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
        submit = adapter.submit_case(popup, case_info.to_dict())
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
    args = parser.parse_args()

    raw_cases = load_cases()
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

