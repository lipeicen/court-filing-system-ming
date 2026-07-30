from dataclasses import dataclass, field
from typing import List, Optional
from enum import Enum
from datetime import datetime

class FilingStatus(Enum):
    # 立案状态
    PENDING = "待提交"
    SUBMITTING = "提交中"
    SUBMITTED = "已提交"
    REVIEWING = "审核中"
    APPROVED = "已通过"
    REJECTED = "已驳回"
    COMPLETED = "已完成"

class CaseType(Enum):
    # 案件类型
    CIVIL = "民事案件"
    CRIMINAL = "刑事案件"
    ADMINISTRATIVE = "行政案件"
    EXECUTION = "执行案件"

@dataclass
class Party:
    # 当事人信息
    name: str
    idcard: str
    phone: str
    address: str = ""
    party_type: str = "原告"  # 原告/被告/第三人
    cert_no: str = ""  # 证件号码（与 idcard 一致，兼容法院页面）
    cert_type: str = "居民身份证"  # 证件类型
    party_category: str = "自然人"  # 自然人/法人/其他组织
    gender: str = ""  # 性别
    nation: str = "汉族"  # 民族
    
    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "idcard": self.idcard,
            "cert_no": self.cert_no or self.idcard,
            "cert_type": self.cert_type,
            "phone": self.phone,
            "address": self.address,
            "party_type": self.party_type,
            "party_category": self.party_category,
            "gender": self.gender,
            "nation": self.nation
        }

@dataclass
class CaseDocument:
    # 案件材料
    name: str
    path: str
    doc_type: str  # 起诉状/身份证明/证据/委托书等
    description: str = ""
    
    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "path": self.path,
            "type": self.doc_type,
            "description": self.description
        }

@dataclass
class CaseInfo:
    # 案件信息
    case_type: str
    court_code: str
    parties: List[Party]
    claims: str
    facts: str
    amount: float
    documents: List[CaseDocument]
    metadata: dict = field(default_factory=dict)
    court_name: str = ""
    
    def to_dict(self) -> dict:
        return {
            "case_type": self.case_type,
            "court_code": self.court_code,
            "court_name": self.court_name,
            "parties": [p.to_dict() for p in self.parties],
            "claims": self.claims,
            "facts": self.facts,
            "amount": self.amount,
            "documents": [d.to_dict() for d in self.documents],
            "metadata": self.metadata
        }

@dataclass
class FilingResult:
    # 立案结果
    case_id: Optional[str] = None
    status: FilingStatus = FilingStatus.PENDING
    message: str = ""
    court_code: str = ""
    court_name: str = ""
    steps: List[dict] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self) -> dict:
        return {
            "case_id": self.case_id,
            "status": self.status.value,
            "message": self.message,
            "court_code": self.court_code,
            "court_name": self.court_name,
            "steps": self.steps,
            "created_at": self.created_at
        }
