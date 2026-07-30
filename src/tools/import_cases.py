#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
案件批量导入工具
- 从 Excel 读取案件数据
- 自动解析案件名称中的原被告
- 根据案由生成默认诉讼请求和事实
- 支持文件路径列（JSON 或目录自动匹配）
- 文件路径存入数据库 case_files，不存文件内容
"""

import os
import sys
import json
import re
import shutil
import argparse
import pymysql
from pathlib import Path
from datetime import datetime
from loguru import logger

try:
    import openpyxl
except ImportError as e:
    raise ImportError("请安装 openpyxl: pip install openpyxl") from e

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "lijiayu123",
    "database": "court_filing_civil_test",
    "charset": "utf8mb4",
}

PROJECT_DIR = BASE_DIR.parent
DEFAULT_FILE_DIR = PROJECT_DIR / "documents" / "cases"
DEFAULT_FILE_DIR.mkdir(parents=True, exist_ok=True)

CATEGORY_NAMES = ["起诉状", "身份证明", "证据", "送达地址确认书", "委托书"]

# 默认源文件映射：当源目录里的文件名按模板生成时，按类别匹配
SOURCE_FILE_MAP = {
    "起诉状": ["civil_complaint.png", "complaint.png", "起诉状"],
    "身份证明": ["plaintiff_id.png", "id.png", "身份证明"],
    "证据": ["contract_evidence.png", "payment_evidence.png", "evidence_contract.png", "evidence_receipt.png", "证据"],
    "送达地址确认书": ["delivery_confirmation.png", "送达地址"],
    "委托书": ["power_of_attorney.png", "委托书"],
}


def normalize_header(h: str) -> str:
    if not h:
        return ""
    h = str(h).strip().replace("*", "").replace(" ", "").replace("\u3000", "")
    return h


HEADER_MAP = {
    "case_no": ["案件编号", "案号", "编号", "case_no"],
    "case_name": ["案件名称", "案名", "case_name"],
    "case_reason": ["案由", "case_reason"],
    "court_name": ["申请法院", "法院", "court_name"],
    "amount": ["保全金额", "金额", "标的金额", "amount"],
    "delivery_address": ["送达地址", "delivery_address"],
    "contact_name": ["联系人姓名", "联系人", "contact_name"],
    "contact_phone": ["联系人电话", "联系电话", "contact_phone"],
    "applicant_type": ["申请人类型", "当事人类型", "applicant_type"],
    "applicant_name": ["申请人姓名", "原告", "申请人", "applicant_name"],
    "applicant_id": ["申请人身份证号", "申请人证件号", "原告身份证号", "applicant_id"],
    "applicant_phone": ["申请人手机号", "申请人电话", "applicant_phone"],
    "applicant_address": ["申请人地址", "原告地址", "applicant_address"],
    "respondent_name": ["被申请人姓名", "被申请人", "被告姓名", "被告", "respondent_name"],
    "respondent_id": ["被申请人身份证号", "被申请人证件号", "被告身份证号", "respondent_id"],
    "respondent_phone": ["被申请人手机号", "被申请人电话", "被告电话", "respondent_phone"],
    "respondent_address": ["被申请人地址", "被告地址", "respondent_address"],
    "claims": ["诉讼请求", "claims"],
    "facts": ["事实与理由", "事实", "facts"],
    "file_paths": ["文件路径", "材料路径", "file_paths"],
    "remarks": ["备注", "remarks"],
}


def detect_columns(headers):
    mapping = {}
    norm = [normalize_header(h) for h in headers]
    for field, candidates in HEADER_MAP.items():
        for c in candidates:
            c_norm = normalize_header(c)
            if c_norm in norm:
                mapping[field] = norm.index(c_norm)
                break
    return mapping


def parse_case_name(case_name: str, applicant_name: str = ""):
    """从案件名称解析原告、被告。示例：张三诉李四借款合同纠纷 -> 原告张三 被告李四"""
    plaintiff = applicant_name
    defendant = ""
    if not case_name:
        return plaintiff, defendant
    m = re.match(r"(.+?)诉(.+?)(?:纠纷|一案|案件|诉讼)?", case_name)
    if m:
        plaintiff = m.group(1).strip()
        defendant = m.group(2).strip()
    return plaintiff, defendant


def default_claims(case_reason: str, amount: float, respondent_name: str) -> str:
    reason = case_reason or "纠纷"
    amount_str = str(amount) if amount else "相关款项"
    templates = {
        "买卖合同": f"判令被告{respondent_name}向原告支付货款人民币{amount_str}元及逾期付款利息。",
        "民间借贷": f"判令被告{respondent_name}偿还借款本金人民币{amount_str}元及利息。",
        "借款合同": f"判令被告{respondent_name}偿还借款本金人民币{amount_str}元及利息。",
        "房屋租赁": f"判令被告{respondent_name}支付拖欠租金人民币{amount_str}元并腾退房屋。",
        "股权转让": f"判令被告{respondent_name}支付股权转让款人民币{amount_str}元。",
    }
    for k, v in templates.items():
        if k in reason:
            return v
    return f"判令被告{respondent_name}向原告支付人民币{amount_str}元及相应损失。"


def default_facts(case_reason: str, applicant_name: str, respondent_name: str) -> str:
    reason = case_reason or "合同"
    return f"原告{applicant_name}与被告{respondent_name}之间存在{reason}关系，被告未履行义务，原告合法权益受损，特提起诉讼。"


def parse_file_paths(raw) -> dict:
    if not raw:
        return {}
    s = str(raw).strip()
    if s.startswith("{"):
        try:
            return json.loads(s)
        except Exception:
            pass
    result = {}
    for part in re.split(r"[;；,，]", s):
        if ":" in part:
            k, v = part.split(":", 1)
            result[k.strip()] = v.strip()
    return result


def ensure_files(case_no: str, file_paths: dict, source_dir: Path = None) -> list:
    """确保文件存在，并整理到规范目录。返回 [(category, file_name, file_path)]"""
    case_dir = DEFAULT_FILE_DIR / case_no
    case_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for cat in CATEGORY_NAMES:
        src = None
        # 1) 从文件路径列直接取
        if cat in file_paths and os.path.exists(file_paths[cat]):
            src = Path(file_paths[cat])
        # 2) 在源目录中按 SOURCE_FILE_MAP 候选文件名匹配
        if not src and source_dir:
            candidates = list(source_dir.glob("*"))
            for cand_name in SOURCE_FILE_MAP.get(cat, []):
                for c in candidates:
                    if cand_name.lower() in c.name.lower():
                        src = c
                        break
                if src:
                    break
            # 3) 兜底：源目录中任意包含类别关键字
            if not src:
                for c in candidates:
                    if cat in c.stem:
                        src = c
                        break
        # 4) 目标目录中已存在的同名文件
        if not src:
            for ext in ["pdf", "png", "jpg"]:
                cand = case_dir / f"{cat}.{ext}"
                if cand.exists():
                    src = cand
                    break
        if src:
            ext = src.suffix.lower()
            dst = case_dir / f"{cat}{ext}"
            if src.resolve() != dst.resolve():
                shutil.copy2(str(src), str(dst))
            results.append((cat, dst.name, str(dst)))
    return results


def import_excel(excel_path: str, replace: bool = False, source_dir: str = None):
    excel_path = Path(excel_path)
    if not excel_path.exists():
        raise FileNotFoundError(f"Excel 不存在: {excel_path}")
    wb = openpyxl.load_workbook(str(excel_path))
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        logger.warning("Excel 为空")
        return 0

    headers = rows[0]
    mapping = detect_columns(headers)
    logger.info(f"检测到列映射: {mapping}")

    if "case_no" not in mapping:
        raise ValueError("Excel 缺少案件编号列")

    conn = pymysql.connect(**DB_CONFIG)
    cursor = conn.cursor()

    inserted = 0
    skipped = 0
    for row in rows[1:]:
        if not row or all(v is None or str(v).strip() == "" for v in row):
            continue
        case_no = str(row[mapping["case_no"]]).strip() if row[mapping["case_no"]] is not None else None
        if not case_no:
            continue

        cursor.execute("SELECT id FROM cases WHERE case_no = %s", (case_no,))
        existing = cursor.fetchone()
        if existing:
            if not replace:
                logger.info(f"跳过已存在案件: {case_no}")
                skipped += 1
                continue
            case_id = existing[0]
            cursor.execute("DELETE FROM case_files WHERE case_id = %s", (case_id,))
        else:
            case_id = None

        def get(field, default=""):
            idx = mapping.get(field)
            if idx is None or idx >= len(row):
                return default
            v = row[idx]
            return str(v).strip() if v is not None else default

        case_name = get("case_name")
        case_reason = get("case_reason")
        court_name = get("court_name")
        amount_raw = get("amount", "0")
        try:
            amount = float(str(amount_raw).replace(",", "").strip()) if amount_raw else 0
        except Exception:
            amount = 0

        applicant_type = get("applicant_type", "自然人")
        applicant_name = get("applicant_name")
        applicant_id = get("applicant_id")
        applicant_phone = get("applicant_phone")
        applicant_address = get("applicant_address")

        parsed_plaintiff, parsed_defendant = parse_case_name(case_name, applicant_name)
        if not applicant_name and parsed_plaintiff:
            applicant_name = parsed_plaintiff

        respondent_name = get("respondent_name")
        if not respondent_name and parsed_defendant:
            respondent_name = parsed_defendant
        if not respondent_name:
            respondent_name = "被告"

        respondent_id = get("respondent_id")
        respondent_phone = get("respondent_phone")
        respondent_address = get("respondent_address")
        respondent_type = "法人" if respondent_name and len(respondent_name) > 6 and ("公司" in respondent_name or "企业" in respondent_name) else "自然人"

        claims = get("claims")
        facts = get("facts")
        if not claims:
            claims = default_claims(case_reason, amount, respondent_name)
        if not facts:
            facts = default_facts(case_reason, applicant_name, respondent_name)

        delivery_address = get("delivery_address", applicant_address)
        contact_name = get("contact_name", applicant_name)
        contact_phone = get("contact_phone", applicant_phone)
        court_code = "beijing" if "北京" in court_name else "default"

        case_values = (
            case_no, case_name, "民事案件", case_reason, court_name, court_code,
            applicant_name, applicant_id, applicant_id, applicant_phone, applicant_address, applicant_type,
            respondent_name, respondent_id, respondent_id, respondent_phone, respondent_address, respondent_type,
            claims, facts, amount, delivery_address, contact_name, contact_phone, 0, None
        )

        if case_id:
            sql = """
                UPDATE cases SET
                    case_name=%s, case_type=%s, case_reason=%s, court_name=%s, court_code=%s,
                    applicant_name=%s, applicant_id=%s, applicant_cert_no=%s, applicant_phone=%s, applicant_address=%s, applicant_type=%s,
                    respondent_name=%s, respondent_id=%s, respondent_cert_no=%s, respondent_phone=%s, respondent_address=%s, respondent_type=%s,
                    claims=%s, facts=%s, amount=%s, delivery_address=%s, contact_name=%s, contact_phone=%s, status=%s, filing_status=%s
                WHERE id=%s
            """
            cursor.execute(sql, case_values[1:] + (case_id,))
        else:
            sql = """
                INSERT INTO cases (
                    case_no, case_name, case_type, case_reason, court_name, court_code,
                    applicant_name, applicant_id, applicant_cert_no, applicant_phone, applicant_address, applicant_type,
                    respondent_name, respondent_id, respondent_cert_no, respondent_phone, respondent_address, respondent_type,
                    claims, facts, amount, delivery_address, contact_name, contact_phone, status, filing_status
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            cursor.execute(sql, case_values)
            case_id = cursor.lastrowid
            inserted += 1

        file_paths_raw = row[mapping.get("file_paths", -1)] if mapping.get("file_paths") is not None and len(row) > mapping.get("file_paths") else None
        file_paths = parse_file_paths(file_paths_raw)
        src_dir = Path(source_dir) if source_dir else None
        files = ensure_files(case_no, file_paths, src_dir)
        for cat, file_name, file_path in files:
            cursor.execute(
                "INSERT INTO case_files (case_id, file_category, file_name, file_path, upload_status) VALUES (%s, %s, %s, %s, %s)",
                (case_id, cat, file_name, file_path, 0)
            )
            logger.info(f"案件 {case_no} 文件: {cat} -> {file_path}")

        conn.commit()
        logger.info(f"导入案件: {case_no} -> {court_name} ({'更新' if existing else '新增'})")

    cursor.close()
    conn.close()
    logger.info(f"完成: 新增 {inserted} 条, 跳过 {skipped} 条")
    return inserted


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="批量导入案件到数据库")
    parser.add_argument("excel", help="Excel 文件路径")
    parser.add_argument("--replace", action="store_true", help="覆盖已存在的案件")
    parser.add_argument("--source-dir", help="材料文件源目录（未指定文件路径时从此目录匹配）")
    parser.add_argument("--log", default="logs/import_cases.log", help="日志路径")
    args = parser.parse_args()

    os.makedirs(os.path.dirname(args.log) or ".", exist_ok=True)
    logger.add(args.log, rotation="10 MB", retention="30 days", encoding="utf-8")

    import_excel(args.excel, replace=args.replace, source_dir=args.source_dir)
