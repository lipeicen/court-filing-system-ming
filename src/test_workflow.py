import pytest
from unittest.mock import Mock, patch
from workflow import FilingWorkflow, CourtAdapterFactory
from models import CaseInfo, Party, CaseDocument, FilingStatus

class TestFilingWorkflow:
    
    def test_create_workflow(self):
        # 测试创建工作流
        workflow = FilingWorkflow()
        assert workflow is not None
        assert workflow.browser_pool is not None
        workflow.close()
    
    def test_adapter_factory(self):
        # 测试适配器工厂
        adapter = CourtAdapterFactory.get_adapter("beijing")
        assert adapter.court_code == "beijing"
        assert adapter.court_name == "北京法院"
    
    def test_adapter_factory_unsupported(self):
        # 测试不支持的法院
        with pytest.raises(ValueError):
            CourtAdapterFactory.get_adapter("unknown")
    
    def test_create_case(self):
        # 测试创建案件
        party = Party(
            name="测试",
            idcard="110101199001011234",
            phone="13800138000",
            party_type="原告"
        )
        
        case = CaseInfo(
            case_type="民事案件",
            court_code="beijing",
            parties=[party],
            claims="测试请求",
            facts="测试事实",
            amount=10000.00,
            documents=[]
        )
        
        assert case.case_type == "民事案件"
        assert len(case.parties) == 1
        assert case.amount == 10000.00

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
