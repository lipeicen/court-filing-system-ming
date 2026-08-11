#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
民事立案案件批量导入工具
- 从 Excel 读取案件数据
- 自动解析案件名称中的原被告（未填写时）
- 根据案由生成默认诉讼请求和事实与理由（未填写时）
- 支持文件路径列（JSON 或分号分隔的类别:路径）
- 文件路径存入数据库 case_files，不存文件内容
- 适用于法院网上立案系统（北京及其他）民事一审
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
    "database": "court_filing_civil",
    "charset": "utf8mb4",
}

PROJECT_DIR = BASE_DIR.parent
DEFAULT_FILE_DIR = PROJECT_DIR / "documents" / "cases"
DEFAULT_FILE_DIR.mkdir(parents=True, exist_ok=True)

CATEGORY_NAMES = [
    "起诉状",
    "当事人身份证明",
    "委托代理人委托手续和身份材料",
    "证据目录及证据材料",
    "送达地址确认书",
    "其他材料",
]

SOURCE_FILE_MAP = {
    "起诉状": ["civil_complaint.png", "complaint.png", "起诉状"],
    "当事人身份证明": ["plaintiff_id.png", "id.png", "身份证明", "身份证"],
    "委托代理人委托手续和身份材料": ["power_of_attorney.png", "委托书", "代理手续", "委托材料"],
    "证据目录及证据材料": ["contract_evidence.png", "payment_evidence.png", "evidence_contract.png", "evidence_receipt.png", "证据"],
    "送达地址确认书": ["delivery_confirmation.png", "送达地址"],
    "其他材料": ["other.png", "其他材料"],
}


def normalize_header(h: str) -> str:
    if not h:
        return ""
    h = str(h).strip().replace("*", "").replace(" ", "").replace("\u3000", "").replace("（", "(").replace("）", ")")
    return h


HEADER_MAP = {
    "case_no": ["案件编号", "案号", "编号", "case_no"],
    "case_name": ["案件名称", "案名", "case_name"],
    "case_reason": ["案由", "case_reason"],
    "court_name": ["申请法院", "法院", "court_name", "受诉法院"],
    "claim_amount": ["诉讼标的金额", "标的金额", "金额", "诉求金额", "claim_amount", "保全金额"],
    "claims": ["诉讼请求", "claim", "claims"],
    "facts": ["事实与理由", "事实理由", "事实", "facts"],
    "delivery_address": ["送达地址", "delivery_address"],
    "contact_name": ["联系人姓名", "联系人", "contact_name"],
    "contact_phone": ["联系人电话", "联系电话", "contact_phone"],
    "remarks": ["备注", "remarks"],
    "file_paths": ["文件路径", "材料路径", "file_paths", "附件路径"],

    "applicant_type": ["申请人类型", "原告类型", "当事人类型", "applicant_type"],
    "applicant_name": ["申请人姓名", "原告", "原告姓名", "申请人", "applicant_name"],
    "applicant_id": ["申请人身份证号", "申请人证件号", "原告身份证号", "applicant_id"],
    "applicant_gender": ["申请人性别", "原告性别", "applicant_gender"],
    "applicant_phone": ["申请人手机号", "申请人电话", "原告手机号", "applicant_phone"],
    "applicant_address": ["申请人地址", "原告地址", "applicant_address"],
    "applicant_email": ["申请人电子邮箱", "申请人邮箱", "原告邮箱", "applicant_email"],
    "applicant_occupation": ["申请人职业", "原告职业", "applicant_occupation"],
    "applicant_residence": ["申请人经常居住地", "applicant_residence"],
    "applicant_unit_name": ["申请人单位名称", "原告单位名称", "applicant_unit_name"],
    "applicant_uscc": ["申请人统一社会信用代码", "applicant_uscc"],
    "applicant_nature": ["申请人单位性质", "原告单位性质", "applicant_nature"],
    "applicant_legal_person": ["申请人法定代表人", "原告法定代表人", "applicant_legal_person"],
    "applicant_legal_title": ["申请人法定代表人职务", "原告法定代表人职务", "applicant_legal_title"],
    "applicant_reg_address": ["申请人单位注册地", "applicant_reg_address"],
    "applicant_tel": ["申请人固定电话", "申请人座机", "applicant_tel"],
    "applicant_nation": ["申请人民族", "原告民族", "applicant_nation"],
    "applicant_birth": ["申请人出生日期", "applicant_birth"],
    "applicant_age": ["申请人年龄", "applicant_age"],

    "respondent_type": ["被申请人类型", "被告类型", "respondent_type"],
    "respondent_name": ["被申请人姓名", "被申请人", "被告姓名", "被告", "respondent_name"],
    "respondent_id": ["被申请人身份证号", "被申请人证件号", "被告身份证号", "respondent_id"],
    "respondent_gender": ["被申请人性别", "被告性别", "respondent_gender"],
    "respondent_phone": ["被申请人手机号", "被申请人电话", "被告电话", "respondent_phone"],
    "respondent_address": ["被申请人地址", "被告地址", "respondent_address"],
    "respondent_email": ["被申请人电子邮箱", "被申请人邮箱", "被告邮箱", "respondent_email"],
    "respondent_occupation": ["被申请人职业", "被告职业", "respondent_occupation"],
    "respondent_residence": ["被申请人经常居住地", "respondent_residence"],
    "respondent_unit_name": ["被申请人单位名称", "被告单位名称", "respondent_unit_name"],
    "respondent_uscc": ["被申请人统一社会信用代码", "respondent_uscc"],
    "respondent_nature": ["被申请人单位性质", "被告单位性质", "respondent_nature"],
    "respondent_legal_person": ["被申请人法定代表人", "被告法定代表人", "respondent_legal_person"],
    "respondent_legal_title": ["被申请人法定代表人职务", "被告法定代表人职务", "respondent_legal_title"],
    "respondent_reg_address": ["被申请人单位注册地", "respondent_reg_address"],
    "respondent_tel": ["被申请人固定电话", "被申请人座机", "respondent_tel"],
    "respondent_nation": ["被申请人民族", "被告民族", "respondent_nation"],
    "respondent_birth": ["被申请人出生日期", "respondent_birth"],
    "respondent_age": ["被申请人年龄", "respondent_age"],

    "agent_type": ["代理人类型", "agent_type"],
    "agent_name": ["代理人姓名", "agent_name"],
    "agent_id": ["代理人身份证号", "agent_id"],
    "agent_phone": ["代理人电话", "agent_phone"],
    "agent_cert_no": ["代理人执业证号", "agent_id"],
    "agent_law_firm": ["代理人律所", "agent_law_firm"],
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
    plaintiff = applicant_name
    defendant = ""
    if not case_name:
        return plaintiff, defendant
    m = re.match(r"(.+?)诉(.+?)(?:纠纷|一案|案件|诉讼)?", case_name)
    if m:
        plaintiff = m.group(1).strip()
        defendant = m.group(2).strip()
    return plaintiff, defendant


def default_claims(case_reason: str, claim_amount: float, respondent_name: str) -> str:
    reason = case_reason or "纠纷"
    amount_str = str(claim_amount) if claim_amount else "相关款项"
    templates = {
        "买卖合同": f"1.判令被告{respondent_name}向原告支付货款人民币{amount_str}元及逾期付款利息；\n2.判令被告承担本案诉讼费用。",
        "民间借贷": f"1.判令被告{respondent_name}偿还借款本金人民币{amount_str}元及利息；\n2.判令被告承担本案诉讼费用。",
        "借款合同": f"1.判令被告{respondent_name}偿还借款本金人民币{amount_str}元及利息；\n2.判令被告承担本案诉讼费用。",
        "房屋租赁": f"1.判令被告{respondent_name}支付拖欠租金人民币{amount_str}元并腾退房屋；\n2.判令被告承担本案诉讼费用。",
        "股权转让": f"1.判令被告{respondent_name}支付股权转让款人民币{amount_str}元；\n2.判令被告承担本案诉讼费用。",
    }
    for k, v in templates.items():
        if k in reason:
            return v
    return f"1.判令被告{respondent_name}向原告支付人民币{amount_str}元及相应损失；\n2.判令被告承担本案诉讼费用。"


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
    for part in re.split(r"[;；]", s):
        if ":" in part:
            k, v = part.split(":", 1)
            result[k.strip()] = v.strip()
    return result


def ensure_files(case_no: str, file_paths: dict, source_dir: Path = None) -> list:
    case_dir = DEFAULT_FILE_DIR / case_no
    case_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for cat in CATEGORY_NAMES:
        src = None
        if cat in file_paths and os.path.exists(file_paths[cat]):
            src = Path(file_paths[cat])
        if not src and source_dir:
            candidates = list(source_dir.glob("*"))
            for cand_name in SOURCE_FILE_MAP.get(cat, []):
                for c in candidates:
                    if cand_name.lower() in c.name.lower():
                        src = c
                        break
                if src:
                    break
            if not src:
                for c in candidates:
                    if cat in c.stem:
                        src = c
                        break
        if not src:
            for ext in [".pdf", ".png", ".jpg", ".jpeg"]:
                cand = case_dir / f"{cat}{ext}"
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


def to_none_or_str(v):
    if v is None:
        return None
    s = str(v).strip()
    return s if s else None


def to_int(v):
    if v is None or str(v).strip() == "":
        return None
    try:
        return int(str(v).strip().replace(",", ""))
    except Exception:
        return None


def to_float(v):
    if v is None or str(v).strip() == "":
        return None
    try:
        return float(str(v).strip().replace(",", "").replace("，", ""))
    except Exception:
        return None


def infer_unit_type(name: str, unit_name: str, uscc: str) -> str:
    if unit_name or uscc:
        return "法人"
    if not name:
        return "自然人"
    if "公司" in name or "企业" in name or "集团" in name or "厂" in name or "店" in name or "中心" in name or "院" in name:
        return "法人"
    return "自然人"


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

        def get(field, default=None):
            idx = mapping.get(field)
            if idx is None or idx >= len(row):
                return default
            v = row[idx]
            if v is None:
                return default
            s = str(v).strip()
            return s if s else default

        case_name = get("case_name")
        case_reason = get("case_reason")
        court_name = get("court_name")
        claim_amount = to_float(get("claim_amount"))
        claims = get("claims")
        facts = get("facts")

        applicant_type = get("applicant_type", "自然人")
        applicant_name = get("applicant_name")
        applicant_id = get("applicant_id")
        applicant_gender = get("applicant_gender")
        applicant_phone = get("applicant_phone")
        applicant_address = get("applicant_address")
        applicant_email = get("applicant_email")
        applicant_occupation = get("applicant_occupation")
        applicant_residence = get("applicant_residence")
        applicant_unit_name = get("applicant_unit_name")
        applicant_uscc = get("applicant_uscc")
        applicant_nature = get("applicant_nature")
        applicant_legal_person = get("applicant_legal_person")
        applicant_legal_title = get("applicant_legal_title")
        applicant_reg_address = get("applicant_reg_address")
        applicant_tel = get("applicant_tel")
        applicant_nation = get("applicant_nation", "汉族")
        applicant_birth = get("applicant_birth")
        applicant_age = to_int(get("applicant_age"))

        parsed_plaintiff, parsed_defendant = parse_case_name(case_name, applicant_name)
        if not applicant_name and parsed_plaintiff:
            applicant_name = parsed_plaintiff

        respondent_type = get("respondent_type")
        respondent_name = get("respondent_name")
        if not respondent_name and parsed_defendant:
            respondent_name = parsed_defendant
        if not respondent_name:
            respondent_name = "被告"
        respondent_id = get("respondent_id")
        respondent_gender = get("respondent_gender")
        respondent_phone = get("respondent_phone")
        respondent_address = get("respondent_address")
        respondent_email = get("respondent_email")
        respondent_occupation = get("respondent_occupation")
        respondent_residence = get("respondent_residence")
        respondent_unit_name = get("respondent_unit_name")
        respondent_uscc = get("respondent_uscc")
        respondent_nature = get("respondent_nature")
        respondent_legal_person = get("respondent_legal_person")
        respondent_legal_title = get("respondent_legal_title")
        respondent_reg_address = get("respondent_reg_address")
        respondent_tel = get("respondent_tel")
        respondent_nation = get("respondent_nation", "汉族")
        respondent_birth = get("respondent_birth")
        respondent_age = to_int(get("respondent_age"))

        if not applicant_type or applicant_type == "自然人":
            applicant_type = infer_unit_type(applicant_name, applicant_unit_name, applicant_uscc)
        if not respondent_type or respondent_type == "自然人":
            respondent_type = infer_unit_type(respondent_name, respondent_unit_name, respondent_uscc)

        if not claims:
            claims = default_claims(case_reason, claim_amount or 0, respondent_name)
        if not facts:
            facts = default_facts(case_reason, applicant_name, respondent_name)

        delivery_address = get("delivery_address", applicant_address)
        contact_name = get("contact_name", applicant_name)
        contact_phone = get("contact_phone", applicant_phone)
        court_code = "beijing" if "北京" in (court_name or "") else "default"

        agent_type = get("agent_type")
        agent_name = get("agent_name")
        agent_id = get("agent_id")
        agent_phone = get("agent_phone")
        agent_cert_no = get("agent_cert_no")
        agent_law_firm = get("agent_law_firm")
        has_agent = 1 if agent_name else 0

        remarks = get("remarks")

        case_values = {
            "case_no": case_no,
            "case_name": case_name,
            "case_type": "民事案件",
            "case_reason": case_reason,
            "court_name": court_name,
            "court_code": court_code,
            "claim_amount": claim_amount,
            "claim": claims,
            "facts": facts,
            "delivery_address": delivery_address,
            "contact_name": contact_name,
            "contact_phone": contact_phone,
            "remark": remarks,

            "applicant_type": applicant_type,
            "applicant_name": applicant_name,
            "applicant_id": applicant_id,
            "applicant_cert_no": applicant_id,
            "applicant_cert_type": "居民身份证" if applicant_id else "身份证",
            "applicant_gender": applicant_gender,
            "applicant_phone": applicant_phone,
            "applicant_tel": applicant_tel or applicant_phone,
            "applicant_address": applicant_address,
            "applicant_email": applicant_email,
            "applicant_occupation": applicant_occupation,
            "applicant_residence": applicant_residence,
            "applicant_nature": applicant_nature,
            "applicant_legal_person": applicant_legal_person,
            "applicant_legal_title": applicant_legal_title,
            "applicant_reg_address": applicant_reg_address,
            "applicant_uscc": applicant_uscc,
            "applicant_nation": applicant_nation,
            "applicant_birth": applicant_birth if applicant_birth else None,
            "applicant_age": applicant_age,

            "respondent_type": respondent_type,
            "respondent_name": respondent_name,
            "respondent_id": respondent_id,
            "respondent_cert_no": respondent_id,
            "respondent_cert_type": "居民身份证" if respondent_id else "身份证",
            "respondent_gender": respondent_gender,
            "respondent_phone": respondent_phone,
            "respondent_tel": respondent_tel or respondent_phone,
            "respondent_address": respondent_address,
            "respondent_email": respondent_email,
            "respondent_occupation": respondent_occupation,
            "respondent_residence": respondent_residence,
            "respondent_nature": respondent_nature,
            "respondent_legal_person": respondent_legal_person,
            "respondent_legal_title": respondent_legal_title,
            "respondent_reg_address": respondent_reg_address,
            "respondent_uscc": respondent_uscc,
            "respondent_nation": respondent_nation,
            "respondent_birth": respondent_birth if respondent_birth else None,
            "respondent_age": respondent_age,

            "agent_type": agent_type,
            "agent_name": agent_name,
                        "agent_id": agent_id or agent_cert_no,
            "agent_phone": agent_phone,
                        "agent_law_firm": agent_law_firm,
            "has_agent": has_agent,

            "status": 0,
            "filing_status": None,
        }

        fields = [k for k, v in case_values.items() if v is not None]
        values = [case_values[k] for k in fields]

        if case_id:
            set_clause = ", ".join([f"{f}=%s" for f in fields])
            sql = f"UPDATE cases SET {set_clause} WHERE id=%s"
            cursor.execute(sql, values + [case_id])
        else:
            sql = f"INSERT INTO cases ({', '.join(fields)}) VALUES ({', '.join(['%s'] * len(fields))})"
            cursor.execute(sql, values)
            case_id = cursor.lastrowid
            inserted += 1

        file_paths_raw = None
        if "file_paths" in mapping and len(row) > mapping["file_paths"]:
            file_paths_raw = row[mapping["file_paths"]]
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
    parser = argparse.ArgumentParser(description="批量导入民事立案案件到数据库")
    parser.add_argument("excel", help="Excel 文件路径")
    parser.add_argument("--replace", action="store_true", help="覆盖已存在的案件")
    parser.add_argument("--source-dir", help="材料文件源目录（未指定文件路径时从此目录匹配）")
    parser.add_argument("--log", default="logs/import_cases.log", help="日志路径")
    args = parser.parse_args()

    os.makedirs(os.path.dirname(args.log) or ".", exist_ok=True)
    logger.remove()
    logger.add(sys.stdout, level="INFO")
    logger.add(args.log, rotation="10 MB", retention="30 days", encoding="utf-8")

    import_excel(args.excel, replace=args.replace, source_dir=args.source_dir)
