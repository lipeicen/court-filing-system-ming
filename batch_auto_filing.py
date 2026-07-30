#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
批量自动立案脚本
从数据库读取待立案案件，自动完成立案流程
"""

import os
import sys
import json
import argparse
from datetime import datetime
from loguru import logger

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from workflow import FilingWorkflow
from models import CaseInfo, Party, CaseDocument, FilingStatus

# 配置日志
os.makedirs("logs", exist_ok=True)
os.makedirs("screenshots", exist_ok=True)
os.makedirs("documents", exist_ok=True)
os.makedirs("results", exist_ok=True)

logger.add(
    "logs/batch_filing.log",
    rotation="10 MB",
    retention="30 days",
    level="INFO",
    encoding="utf-8"
)


def load_pending_cases():
    """从数据库加载待立案案件"""
    try:
        import pymysql
        conn = pymysql.connect(
            host='localhost',
            user='root',
            password='lijiayu123',
            database='court_filing_civil_test',
            charset='utf8mb4'
        )
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        
        # 查询待立案案件 (status = 0)
        cursor.execute("""
            SELECT c.*,
                   (SELECT JSON_ARRAYAGG(JSON_OBJECT('category', cf.file_category, 'path', cf.file_path, 'name', cf.file_name))
                    FROM case_files cf WHERE cf.case_id = c.id) AS file_list
            FROM cases c
            WHERE c.status = 0
            ORDER BY c.created_at DESC
            LIMIT 10
        """)
        
        cases = cursor.fetchall()
        cursor.close()
        conn.close()
        
        logger.info(f"从数据库加载了 {len(cases)} 个待立案案件")
        return cases
        
    except Exception as e:
        logger.error(f"加载案件失败: {e}")
        return []


def db_case_to_case_info(db_case):
    """将数据库案件转换为 CaseInfo 对象"""
    
    # 解析当事人信息
    parties = []
    
    # 原告
    plaintiff = Party(
        name=db_case.get('applicant_name', ''),
        idcard=db_case.get('applicant_id', ''),
        cert_no=db_case.get('applicant_cert_no', '') or db_case.get('applicant_id', ''),
        phone=db_case.get('applicant_phone', ''),
        address=db_case.get('applicant_address', ''),
        party_type="原告",
        party_category=db_case.get('applicant_type', '自然人') or '自然人',
        gender='',
        nation='汉族'
    )
    parties.append(plaintiff)
    
    # 被告
    if db_case.get('respondent_name'):
        defendant = Party(
            name=db_case['respondent_name'],
            idcard=db_case.get('respondent_id', ''),
            cert_no=db_case.get('respondent_cert_no', '') or db_case.get('respondent_id', ''),
            phone=db_case.get('respondent_phone', ''),
            address=db_case.get('respondent_address', ''),
            party_type="被告",
            party_category=db_case.get('respondent_type', '自然人') or '自然人',
            gender='',
            nation='汉族'
        )
        parties.append(defendant)
    
    # 文档列表：从 case_files JSON 解析
    documents = []
    file_list = db_case.get('file_list') or ''
    if file_list:
        try:
            arr = json.loads(file_list)
            for item in arr:
                documents.append(CaseDocument(
                    name=item.get('name', ''),
                    path=item.get('path', ''),
                    doc_type=item.get('category', ''),
                    description=item.get('category', '')
                ))
        except Exception as e:
            logger.warning(f"解析 file_list 失败: {e}")
    
    case = CaseInfo(
        case_type=db_case.get('case_type', '民事案件'),
        court_code=db_case.get('court_code', 'beijing'),
        court_name=db_case.get('court_name', ''),
        parties=parties,
        claims=db_case.get('claims', ''),
        facts=db_case.get('facts', ''),
        amount=float(db_case.get('amount', 0) or 0),
        documents=documents,
        metadata={
            "case_no": db_case.get('case_no', ''),
            "case_cause": db_case.get('case_reason', '买卖合同纠纷')
        }
    )
    
    return case


def update_case_status(case_no, status, message='', case_id=''):
    """更新案件状态"""
    try:
        import pymysql
        conn = pymysql.connect(
            host='localhost',
            user='root',
            password='lijiayu123',
            database='court_filing_civil_test',
            charset='utf8mb4'
        )
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE cases 
            SET status = %s, 
                filing_status = %s,
                updated_at = NOW()
            WHERE case_no = %s
        """, (status, message, case_no))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        logger.info(f"案件 {case_no} 状态已更新为: {status}")
        
    except Exception as e:
        logger.error(f"更新案件状态失败: {e}")


def batch_auto_filing(max_cases=5, dry_run=False):
    """批量自动立案"""
    
    logger.info(f"=== 批量自动立案开始 (max={max_cases}, dry_run={dry_run}) ===")
    
    # 加载待立案案件
    db_cases = load_pending_cases()
    if not db_cases:
        logger.info("没有待立案案件")
        return
    
    # 限制数量
    db_cases = db_cases[:max_cases]
    
    # 创建工作流
    workflow = FilingWorkflow()
    
    results = {
        "total": len(db_cases),
        "success": 0,
        "failed": 0,
        "details": []
    }
    
    try:
        for i, db_case in enumerate(db_cases, 1):
            case_no = db_case.get('case_no', f'case_{i}')
            logger.info(f"\n--- 处理案件 {i}/{len(db_cases)}: {case_no} ---")
            
            try:
                # 转换为 CaseInfo
                case_info = db_case_to_case_info(db_case)
                
                if dry_run:
                    logger.info(f"[DRY RUN] 跳过实际立案: {case_no}")
                    results["details"].append({
                        "case_no": case_no,
                        "status": "dry_run",
                        "message": "模拟运行，未实际提交"
                    })
                    continue
                
                # 执行立案
                result = workflow.execute(case_info)
                
                # 记录结果
                if result.status == FilingStatus.SUBMITTED:
                    logger.info(f"立案成功: {case_no} -> {result.case_id}")
                    update_case_status(
                        case_no, 
                        status=1,  # 已立案
                        message=result.message,
                        case_id=result.case_id or ''
                    )
                    results["success"] += 1
                else:
                    logger.warning(f"立案失败: {case_no} - {result.message}")
                    update_case_status(
                        case_no,
                        status=2,  # 立案失败
                        message=result.message
                    )
                    results["failed"] += 1
                
                results["details"].append({
                    "case_no": case_no,
                    "status": result.status.value,
                    "case_id": result.case_id,
                    "message": result.message
                })
                
            except Exception as e:
                logger.error(f"处理案件 {case_no} 时出错: {e}")
                update_case_status(case_no, status=2, message=str(e))
                results["failed"] += 1
                results["details"].append({
                    "case_no": case_no,
                    "status": "error",
                    "message": str(e)
                })
    
    finally:
        workflow.close()
    
    # 保存结果报告
    result_file = f"results/batch_result_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(result_file, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    logger.info(f"\n=== 批量自动立案完成 ===")
    logger.info(f"总计: {results['total']}, 成功: {results['success']}, 失败: {results['failed']}")
    logger.info(f"结果报告: {result_file}")
    
    return results


def single_case_filing(case_no: str, dry_run: bool = False):
    """单个案件立案"""
    try:
        import pymysql
        conn = pymysql.connect(
            host='localhost', user='root', password='lijiayu123',
            database='court_filing_civil_test', charset='utf8mb4'
        )
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        sql = """
            SELECT c.*,
                   (SELECT JSON_ARRAYAGG(JSON_OBJECT('category', cf.file_category, 'path', cf.file_path, 'name', cf.file_name))
                    FROM case_files cf WHERE cf.case_id = c.id) AS file_list
            FROM cases c WHERE c.case_no = %s AND c.status = 0
        """
        cursor.execute(sql, (case_no,))
        row = cursor.fetchone()
        cursor.close()
        conn.close()
        if not row:
            logger.warning(f"未找到待立案案件: {case_no}")
            return
        case_info = db_case_to_case_info(row)
        workflow = FilingWorkflow(headless=False)
        if dry_run:
            logger.info(f"[DRY RUN] 案件信息: {case_info.to_dict()}")
            update_case_status(case_no, status=1, message="模拟运行成功")
        else:
            result = workflow.execute(case_info)
            status_code = 1 if result.status.name in ['SUBMITTED', 'APPROVED', 'COMPLETED'] else 2
            update_case_status(case_no, status=status_code, message=result.message)
            logger.info(f"案件 {case_no} 结果: {result.status.value} - {result.message}")
        workflow.close()
    except Exception as e:
        logger.error(f"单案件立案失败: {e}")


def main():
    parser = argparse.ArgumentParser(description='批量自动立案工具')
    parser.add_argument('--max', type=int, default=5, help='最大处理案件数 (默认: 5)')
    parser.add_argument('--dry-run', action='store_true', help='模拟运行，不实际提交')
    parser.add_argument('--case-no', type=str, help='指定单个案件号立案')
    
    args = parser.parse_args()
    
    if args.case_no:
        # 单案件立案模式
        logger.info(f"单案件立案: {args.case_no}")
        single_case_filing(args.case_no, dry_run=args.dry_run)
    else:
        # 批量立案模式
        batch_auto_filing(max_cases=args.max, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
