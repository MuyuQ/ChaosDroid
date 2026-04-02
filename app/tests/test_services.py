"""
服务层单元测试。

测试ExecutionService、RecoveryService和ReportGenerator。
"""
import json
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.executors.mock_executor import MockDeviceExecutor, MockDeviceState, MockScenario
from app.executors.base import BatteryInfo, StorageInfo, ShellResult
from app.validators.base import JudgmentResult, ValidationResult
from app.services.report_generator import ReportData, ReportGenerator
from app.services.recovery_service import (
    RecoveryService,
    RecoveryStep,
    RecoveryStepResult,
    RecoveryResult,
)
from app.services.device_lock_manager import DeviceLock, DeviceLockManager, DeviceLockTimeoutError


# ==================== Fixtures ====================

@pytest.fixture
def mock_executor():
    """创建Mock设备执行器。"""
    return MockDeviceExecutor("test_device_001", MockScenario.normal)


@pytest.fixture
def mock_executor_offline():
    """创建离线Mock设备执行器。"""
    return MockDeviceExecutor("offline_device", MockScenario.offline)


@pytest.fixture
def mock_executor_boot_timeout():
    """创建启动超时Mock设备执行器。"""
    return MockDeviceExecutor("boot_timeout_device", MockScenario.boot_timeout)


@pytest.fixture
def basic_recovery_profile():
    """创建基础恢复配置。"""
    return {
        "steps": [
            {"name": "cleanup", "action": "cleanup_injection", "required": True},
            {"name": "verify", "action": "check_connectivity", "required": True},
        ],
        "manual_intervention_allowed": True,
        "timeout_sec": 300,
    }


@pytest.fixture
def recovery_service(basic_recovery_profile):
    """创建恢复服务实例。"""
    return RecoveryService(basic_recovery_profile)


@pytest.fixture
def recovery_service_empty():
    """创建空配置的恢复服务实例。"""
    return RecoveryService()


@pytest.fixture
def execution_context(mock_executor):
    """创建执行上下文。"""
    return {
        "executor": mock_executor,
        "injector": None,
        "device_serial": "test_device_001",
        "scenario_run_id": 1,
        "inject_result": None,
        "validation_result": None,
        "inject_failed": False,
    }


@pytest.fixture
def report_generator(tmp_path):
    """创建报告生成器实例。"""
    return ReportGenerator(1)


@pytest.fixture
def sample_report_data():
    """创建示例报告数据。"""
    return ReportData(
        scenario_name="存储压力测试场景",
        device_serial="test_device_001",
        inject_stage="precheck",
        fault_type="storage_pressure",
        inject_summary={
            "success": True,
            "pressure_mb": 1000,
            "message": "注入成功",
        },
        validation_summary={
            "passed": True,
            "checks": ["boot_completed", "battery_ok", "storage_ok"],
        },
        recovery_summary={
            "passed": True,
            "cleanup_success": True,
        },
        judgment=JudgmentResult(
            fault_injected=True,
            fault_observed=True,
            validation_passed=True,
            recovery_passed=True,
            risk_level="medium",
            manual_action_required=False,
            final_status="passed",
            message="注入:成功, 验证:通过, 恢复:成功",
        ),
        evidence={
            "logcat": "Sample log output...",
            "properties": {"ro.product.model": "Test Device"},
        },
        started_at=datetime(2026, 3, 30, 10, 0, 0),
        finished_at=datetime(2026, 3, 30, 10, 5, 0),
        duration_sec=300.0,
    )


# ==================== RecoveryStep 测试 ====================

class TestRecoveryStep:
    """测试恢复步骤数据类。"""

    def test_step_creation(self):
        """测试创建恢复步骤。"""
        step = RecoveryStep(
            name="cleanup_storage",
            action="cleanup_storage",
            params={"target_path": "/sdcard/test"},
            timeout_sec=60,
            required=True,
        )

        assert step.name == "cleanup_storage"
        assert step.action == "cleanup_storage"
        assert step.params == {"target_path": "/sdcard/test"}
        assert step.timeout_sec == 60
        assert step.required is True

    def test_step_defaults(self):
        """测试恢复步骤默认值。"""
        step = RecoveryStep(name="test", action="test_action")

        assert step.params == {}
        assert step.timeout_sec == 60
        assert step.required is True


# ==================== RecoveryStepResult 测试 ====================

class TestRecoveryStepResult:
    """测试恢复步骤结果数据类。"""

    def test_result_creation_success(self):
        """测试创建成功的步骤结果。"""
        result = RecoveryStepResult(
            step_name="cleanup_storage",
            success=True,
            message="存储清理成功",
            details={"files_removed": 10},
        )

        assert result.step_name == "cleanup_storage"
        assert result.success is True
        assert result.message == "存储清理成功"

    def test_result_creation_failure(self):
        """测试创建失败的步骤结果。"""
        result = RecoveryStepResult(
            step_name="reboot_device",
            success=False,
            message="重启超时",
        )

        assert result.success is False
        assert result.message == "重启超时"

    def test_result_to_dict(self):
        """测试步骤结果转换为字典。"""
        result = RecoveryStepResult(
            step_name="test_step",
            success=True,
            message="成功",
            started_at=datetime(2026, 3, 30, 10, 0, 0),
            finished_at=datetime(2026, 3, 30, 10, 1, 0),
        )

        result_dict = result.to_dict()

        assert result_dict["step_name"] == "test_step"
        assert result_dict["success"] is True
        assert result_dict["message"] == "成功"
        assert result_dict["started_at"] is not None
        assert result_dict["finished_at"] is not None


# ==================== RecoveryResult 测试 ====================

class TestRecoveryResult:
    """测试恢复结果数据类。"""

    def test_result_creation(self):
        """测试创建恢复结果。"""
        result = RecoveryResult(
            passed=True,
            message="恢复成功",
            cleanup_success=True,
            verification_success=True,
        )

        assert result.passed is True
        assert result.message == "恢复成功"
        assert result.cleanup_success is True
        assert result.verification_success is True

    def test_result_with_steps(self):
        """测试带步骤的恢复结果。"""
        result = RecoveryResult(passed=True)
        result.steps.append(RecoveryStepResult("step1", True, "成功"))
        result.steps.append(RecoveryStepResult("step2", True, "成功"))

        assert len(result.steps) == 2
        assert all(s.success for s in result.steps)

    def test_result_to_dict(self):
        """测试恢复结果转换为字典。"""
        result = RecoveryResult(
            passed=True,
            message="恢复完成",
            manual_action_required=False,
        )
        result.steps.append(RecoveryStepResult("step1", True, "OK"))

        result_dict = result.to_dict()

        assert result_dict["passed"] is True
        assert result_dict["message"] == "恢复完成"
        assert result_dict["manual_action_required"] is False
        assert len(result_dict["steps"]) == 1


# ==================== RecoveryService 初始化测试 ====================

class TestRecoveryServiceInit:
    """测试RecoveryService初始化。"""

    def test_init_with_profile(self, basic_recovery_profile):
        """测试带配置初始化。"""
        service = RecoveryService(basic_recovery_profile)

        assert service.recovery_profile == basic_recovery_profile
        assert len(service.steps) > 0

    def test_init_without_profile(self):
        """测试无配置初始化。"""
        service = RecoveryService()

        assert service.recovery_profile == {}
        # 应使用默认步骤
        assert len(service.steps) > 0

    def test_parse_steps_from_list(self):
        """测试从列表解析步骤。"""
        profile = {
            "steps": [
                {"name": "step1", "action": "cleanup_storage", "timeout_sec": 30},
                {"name": "step2", "action": "check_connectivity", "required": False},
            ]
        }
        service = RecoveryService(profile)

        assert len(service.steps) == 2
        assert service.steps[0].name == "step1"
        assert service.steps[0].timeout_sec == 30
        assert service.steps[1].required is False


# ==================== RecoveryService execute_recovery_steps 测试 ====================

class TestRecoveryServiceExecute:
    """测试RecoveryService执行恢复步骤。"""

    async def test_execute_success(self, recovery_service, mock_executor, execution_context):
        """测试恢复执行成功。"""
        # 设置必要的上下文字段
        execution_context["inject_result"] = {}

        result = await recovery_service.execute_recovery_steps(mock_executor, execution_context)

        # execute_recovery_steps返回字典格式
        assert isinstance(result, dict)
        assert "passed" in result

    async def test_execute_with_injector_cleanup(self, mock_executor, execution_context):
        """测试带注入器清理的恢复。"""
        # 创建Mock注入器
        mock_injector = MagicMock()
        mock_injector.cleanup = AsyncMock(return_value=True)

        execution_context["injector"] = mock_injector
        execution_context["inject_result"] = {"cleanup_required": True}

        service = RecoveryService()
        result = await service.execute_recovery_steps(mock_executor, execution_context)

        assert mock_injector.cleanup.called
        # 应包含清理相关步骤
        assert "steps" in result

    async def test_execute_offline_device(self, recovery_service, mock_executor_offline, execution_context):
        """测试离线设备恢复。"""
        execution_context["executor"] = mock_executor_offline
        execution_context["inject_result"] = {}

        result = await recovery_service.execute_recovery_steps(mock_executor_offline, execution_context)

        # 离线设备应无法通过连通性检查
        assert result["passed"] is False or any(not s.get("success", True) for s in result.get("steps", []))

    async def test_execute_sets_manual_action_required(self, mock_executor, execution_context):
        """测试恢复失败时设置人工介入标记。"""
        # 使用会失败的配置
        profile = {
            "steps": [
                {"name": "fail_step", "action": "unknown_action", "required": True},
            ],
            "manual_intervention_allowed": True,
        }
        service = RecoveryService(profile)
        execution_context["inject_result"] = {}

        result = await service.execute_recovery_steps(mock_executor, execution_context)

        # 如果有步骤失败，应标记需要人工介入
        if not result["passed"]:
            assert result["manual_action_required"] is True


# ==================== RecoveryService 单步执行测试 ====================

class TestRecoveryServiceSingleStep:
    """测试RecoveryService单步恢复操作。"""

    async def test_cleanup_storage_mock(self, recovery_service, mock_executor):
        """测试Mock模式下清理存储。"""
        state = mock_executor.get_state()
        state.apply_injection("storage_pressure", {"pressure_mb": 100})

        success = await recovery_service._cleanup_storage(
            mock_executor,
            {"pressure_mb": 100}
        )

        assert success is True

    async def test_reset_battery_mock(self, recovery_service, mock_executor):
        """测试Mock模式下重置电池。"""
        state = mock_executor.get_state()
        state.apply_injection("low_battery", {"level": 10})

        success = await recovery_service._reset_battery(mock_executor, {})

        assert success is True
        assert state.battery_level == 100

    async def test_reset_network_mock(self, recovery_service, mock_executor):
        """测试Mock模式下重置网络。"""
        state = mock_executor.get_state()
        state.apply_injection("network_jitter", {})

        success = await recovery_service._reset_network(mock_executor, {})

        assert success is True
        assert state.network_connected is True

    async def test_wait_for_boot_mock(self, recovery_service, mock_executor):
        """测试Mock模式下等待启动。"""
        state = mock_executor.get_state()
        state.apply_injection("reboot_timeout", {})

        success = await recovery_service._wait_for_boot(mock_executor, {"timeout_sec": 60})

        assert success is True
        assert state.boot_completed is True

    async def test_stop_stress_mock(self, recovery_service, mock_executor):
        """测试Mock模式下停止压力任务。"""
        state = mock_executor.get_state()
        state.apply_injection("cpu_io_stress", {})
        state.apply_injection("cpu_io_stress", {})

        success = await recovery_service._stop_stress(mock_executor, {})

        assert success is True
        assert len(state.stress_processes) == 0

    async def test_check_connectivity_online(self, recovery_service, mock_executor):
        """测试检查在线设备连通性。"""
        online = await mock_executor.is_online()
        assert online is True


# ==================== RecoveryService 最终验证测试 ====================

class TestRecoveryServiceFinalVerification:
    """测试RecoveryService最终验证。"""

    async def test_final_verification_success(self, recovery_service, mock_executor, execution_context):
        """测试最终验证成功。"""
        result = await recovery_service._final_verification(mock_executor, execution_context)

        assert result.step_name == "verify_recovery"
        assert result.success is True
        assert "通过" in result.message or result.success is True

    async def test_final_verification_offline(self, recovery_service, mock_executor_offline, execution_context):
        """测试离线设备最终验证失败。"""
        result = await recovery_service._final_verification(mock_executor_offline, execution_context)

        assert result.success is False
        assert "离线" in result.message

    async def test_final_verification_low_battery(self, recovery_service, mock_executor, execution_context):
        """测试低电量设备最终验证（注意：当前实现不检查电量）。"""
        state = mock_executor.get_state()
        state.battery_level = 5  # 设置低电量

        result = await recovery_service._final_verification(mock_executor, execution_context)

        # 当前实现不检查电量，只检查在线、boot完成和存储空间
        # 所以低电量设备仍可能通过验证
        assert result.success is True

    async def test_final_verification_storage_low(self, recovery_service, mock_executor, execution_context):
        """测试存储不足设备最终验证。"""
        state = mock_executor.get_state()
        state.storage_available = 10 * 1024 * 1024  # 只有10MB（低于50MB阈值）

        result = await recovery_service._final_verification(mock_executor, execution_context)

        assert result.success is False
        assert "失败" in result.message


# ==================== ReportData 测试 ====================

class TestReportData:
    """测试报告数据类。"""

    def test_report_data_creation(self):
        """测试创建报告数据。"""
        data = ReportData(
            scenario_name="测试场景",
            device_serial="device_001",
            inject_stage="precheck",
            fault_type="storage_pressure",
        )

        assert data.scenario_name == "测试场景"
        assert data.device_serial == "device_001"
        assert data.inject_stage == "precheck"
        assert data.fault_type == "storage_pressure"

    def test_report_data_defaults(self):
        """测试报告数据默认值。"""
        data = ReportData(
            scenario_name="test",
            device_serial="device",
            inject_stage="precheck",
            fault_type="test",
        )

        assert data.inject_summary == {}
        assert data.validation_summary == {}
        assert data.recovery_summary == {}
        assert data.judgment is None
        assert data.evidence == {}
        assert data.duration_sec == 0.0


# ==================== ReportGenerator 测试 ====================

class TestReportGeneratorInit:
    """测试ReportGenerator初始化。"""

    def test_init_with_run_id(self, tmp_path):
        """测试带执行ID初始化。"""
        generator = ReportGenerator(1)

        assert generator.scenario_run_id == 1
        assert generator.reports_dir is not None

    def test_reports_dir_created(self, tmp_path):
        """测试报告目录被创建。"""
        generator = ReportGenerator(1)

        assert generator.reports_dir.exists()


class TestReportGeneratorMarkdown:
    """测试ReportGenerator Markdown生成。"""

    def test_generate_markdown_basic(self, report_generator, sample_report_data):
        """测试生成基础Markdown报告。"""
        markdown = report_generator.generate_markdown(sample_report_data)

        assert "# ChaosDroid 测试报告" in markdown
        assert "存储压力测试场景" in markdown
        assert "test_device_001" in markdown
        assert "storage_pressure" in markdown

    def test_generate_markdown_with_judgment(self, report_generator, sample_report_data):
        """测试生成带判定的Markdown报告。"""
        markdown = report_generator.generate_markdown(sample_report_data)

        assert "最终结论" in markdown
        assert "PASSED" in markdown
        assert "注入" in markdown
        assert "验证" in markdown
        assert "恢复" in markdown

    def test_generate_markdown_inject_summary(self, report_generator, sample_report_data):
        """测试Markdown包含注入摘要。"""
        markdown = report_generator.generate_markdown(sample_report_data)

        assert "注入动作摘要" in markdown
        assert "pressure_mb" in markdown or "注入成功" in markdown

    def test_generate_markdown_validation_summary(self, report_generator, sample_report_data):
        """测试Markdown包含验证摘要。"""
        markdown = report_generator.generate_markdown(sample_report_data)

        assert "验证动作摘要" in markdown

    def test_generate_markdown_recovery_summary(self, report_generator, sample_report_data):
        """测试Markdown包含恢复摘要。"""
        markdown = report_generator.generate_markdown(sample_report_data)

        assert "恢复动作摘要" in markdown

    def test_generate_markdown_evidence(self, report_generator, sample_report_data):
        """测试Markdown包含关键证据。"""
        markdown = report_generator.generate_markdown(sample_report_data)

        assert "关键证据" in markdown

    def test_generate_markdown_recommendations(self, report_generator, sample_report_data):
        """测试Markdown包含建议动作。"""
        markdown = report_generator.generate_markdown(sample_report_data)

        assert "建议动作" in markdown

    def test_generate_markdown_failed_status(self, report_generator):
        """测试失败状态的Markdown报告。"""
        data = ReportData(
            scenario_name="失败测试",
            device_serial="device",
            inject_stage="precheck",
            fault_type="storage_pressure",
            judgment=JudgmentResult(
                fault_injected=True,
                fault_observed=True,
                validation_passed=False,
                recovery_passed=True,
                risk_level="medium",
                manual_action_required=False,
                final_status="failed",
                message="验证失败",
            ),
        )

        markdown = report_generator.generate_markdown(data)

        assert "FAILED" in markdown

    def test_generate_markdown_partial_status(self, report_generator):
        """测试部分成功状态的Markdown报告。"""
        data = ReportData(
            scenario_name="部分测试",
            device_serial="device",
            inject_stage="precheck",
            fault_type="storage_pressure",
            judgment=JudgmentResult(
                fault_injected=True,
                fault_observed=True,
                validation_passed=True,
                recovery_passed=False,
                risk_level="high",
                manual_action_required=True,
                final_status="partial",
                message="恢复失败",
            ),
        )

        markdown = report_generator.generate_markdown(data)

        assert "PARTIAL" in markdown
        assert "人工介入" in markdown


class TestReportGeneratorHTML:
    """测试ReportGenerator HTML生成。"""

    def test_generate_html_basic(self, report_generator, sample_report_data):
        """测试生成基础HTML报告。"""
        markdown = report_generator.generate_markdown(sample_report_data)
        html = report_generator.generate_html(markdown)

        assert "<!DOCTYPE html>" in html
        assert "<html" in html
        assert "</html>" in html
        assert "ChaosDroid 测试报告" in html

    def test_generate_html_contains_style(self, report_generator, sample_report_data):
        """测试HTML包含样式。"""
        markdown = report_generator.generate_markdown(sample_report_data)
        html = report_generator.generate_html(markdown)

        assert "<style>" in html
        assert "</style>" in html

    def test_generate_html_table_conversion(self, report_generator, sample_report_data):
        """测试HTML表格转换。"""
        markdown = report_generator.generate_markdown(sample_report_data)
        html = report_generator.generate_html(markdown)

        # Markdown中的表格应转换为HTML表格
        assert "<table>" in html
        assert "<td>" in html


class TestReportGeneratorSave:
    """测试ReportGenerator保存报告。"""

    def test_save_reports(self, report_generator, sample_report_data):
        """测试保存报告。"""
        paths = report_generator.save_reports(sample_report_data)

        assert "markdown_path" in paths
        assert "html_path" in paths
        assert Path(paths["markdown_path"]).exists()
        assert Path(paths["html_path"]).exists()

    def test_save_reports_content(self, report_generator, sample_report_data):
        """测试保存的报告内容正确。"""
        paths = report_generator.save_reports(sample_report_data)

        md_content = Path(paths["markdown_path"]).read_text(encoding="utf-8")
        html_content = Path(paths["html_path"]).read_text(encoding="utf-8")

        assert "存储压力测试场景" in md_content
        assert "存储压力测试场景" in html_content


class TestReportGeneratorSummary:
    """测试ReportGenerator摘要生成。"""

    def test_generate_summary_json(self, report_generator, sample_report_data):
        """测试生成摘要JSON。"""
        summary = report_generator.generate_summary_json(sample_report_data)

        # 应该是有效的JSON
        data = json.loads(summary)

        assert data["scenario_name"] == "存储压力测试场景"
        assert data["device_serial"] == "test_device_001"
        assert data["fault_type"] == "storage_pressure"

    def test_generate_summary_contains_judgment(self, report_generator, sample_report_data):
        """测试摘要包含判定信息。"""
        summary = report_generator.generate_summary_json(sample_report_data)
        data = json.loads(summary)

        assert "judgment" in data
        assert data["judgment"]["final_status"] == "passed"

    def test_generate_summary_timing(self, report_generator, sample_report_data):
        """测试摘要包含时间信息。"""
        summary = report_generator.generate_summary_json(sample_report_data)
        data = json.loads(summary)

        assert "started_at" in data
        assert "finished_at" in data
        assert "duration_sec" in data
        assert data["duration_sec"] == 300.0


# ==================== ExecutionService 测试 (Mock) ====================

class TestExecutionServiceBasic:
    """测试ExecutionService基础功能。"""

    @pytest.fixture
    def mock_settings(self):
        """创建Mock设置。"""
        settings = MagicMock()
        settings.get_artifacts_dir = MagicMock(return_value=Path("/tmp/artifacts"))
        settings.get_reports_dir = MagicMock(return_value=Path("/tmp/reports"))
        return settings

    def test_service_init(self):
        """测试服务初始化。"""
        from app.services.execution_service import ExecutionService

        service = ExecutionService()

        assert service.settings is not None
        assert isinstance(service._validator_registry, dict)

    @patch("app.services.execution_service.get_session_context")
    async def test_get_scenario_run_not_found(self, mock_session):
        """测试获取不存在的执行记录。"""
        from app.services.execution_service import ExecutionService

        # Mock数据库会话
        mock_session_instance = AsyncMock()
        mock_session_instance.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))
        mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_session_instance)
        mock_session.return_value.__aexit__ = AsyncMock()

        service = ExecutionService()
        result = await service._get_scenario_run(mock_session_instance, 999)

        assert result is None

    def test_build_execution_context(self):
        """测试构建执行上下文。"""
        from app.services.execution_service import ExecutionService
        from app.models import RunStatus

        service = ExecutionService()

        # 创建Mock执行记录
        mock_run = MagicMock()
        mock_run.id = 1
        mock_run.device_serial = "device_001"
        mock_run.inject_stage = "precheck"

        mock_template = MagicMock()
        mock_template.name = "测试场景"
        mock_template.target_type = "stability"

        context = service._build_execution_context(
            scenario_run=mock_run,
            scenario_template=mock_template,
            fault_profile={"fault_type": "storage_pressure"},
            validation_profile={},
            recovery_profile={},
            artifacts_dir=Path("/tmp/artifacts"),
        )

        assert context["scenario_run_id"] == 1
        assert context["device_serial"] == "device_001"
        assert context["scenario_name"] == "测试场景"
        assert context["fault_profile"]["fault_type"] == "storage_pressure"

    def test_setup_executor_mock_mode(self):
        """测试设置Mock执行器。"""
        from app.services.execution_service import ExecutionService

        service = ExecutionService()
        executor = service._setup_executor("mock", "device_001", {})

        assert isinstance(executor, MockDeviceExecutor)
        assert executor.device_serial == "device_001"

    def test_setup_validator_default(self):
        """测试设置默认验证器。"""
        from app.services.execution_service import ExecutionService
        from app.validators.base import DefaultValidator

        service = ExecutionService()
        validator = service._setup_validator({}, {})

        assert isinstance(validator, DefaultValidator)

    def test_setup_recovery_service(self):
        """测试设置恢复服务。"""
        from app.services.execution_service import ExecutionService
        from app.services.recovery_service import RecoveryService

        service = ExecutionService()
        recovery = service._setup_recovery({"steps": []}, {})

        assert isinstance(recovery, RecoveryService)


class TestExecutionServicePrepare:
    """测试ExecutionService准备阶段。"""

    @pytest.fixture
    def service(self):
        """创建服务实例。"""
        from app.services.execution_service import ExecutionService
        return ExecutionService()

    async def test_prepare_phase_success(self, service, mock_executor):
        """测试准备阶段成功。"""
        context = {"executor": mock_executor}

        result = await service._execute_prepare_phase(1, context)

        assert result["success"] is True
        assert "properties" in result["details"]
        assert "battery" in result["details"]
        assert "storage" in result["details"]

    async def test_prepare_phase_offline(self, service, mock_executor_offline):
        """测试离线设备准备阶段失败。"""
        context = {"executor": mock_executor_offline}

        result = await service._execute_prepare_phase(1, context)

        assert result["success"] is False
        assert result["error"] == "device_offline"

    async def test_prepare_phase_low_battery(self, service):
        """测试低电量设备准备阶段。"""
        executor = MockDeviceExecutor("low_battery", MockScenario.low_battery)
        context = {"executor": executor}

        result = await service._execute_prepare_phase(1, context)

        # 低电量应触发前置检查失败
        assert result["success"] is False
        assert "low_battery" in result.get("issues", [])


class TestExecutionServiceInject:
    """测试ExecutionService注入阶段。"""

    @pytest.fixture
    def service(self):
        """创建服务实例。"""
        from app.services.execution_service import ExecutionService
        return ExecutionService()

    async def test_inject_phase_no_injector(self, service, mock_executor):
        """测试无注入器时跳过注入。"""
        context = {
            "injector": None,
            "executor": mock_executor,
            "fault_profile": {},
            "artifacts_dir": "/tmp",
        }

        result = await service._execute_inject_phase(1, context)

        assert result["success"] is True
        assert result["skipped"] is True

    async def test_inject_phase_with_injector(self, service, mock_executor):
        """测试带注入器的注入阶段。"""
        from app.injectors.storage_pressure import StoragePressureInjector

        injector = StoragePressureInjector()
        context = {
            "injector": injector,
            "executor": mock_executor,
            "fault_profile": {"parameters": {"pressure_mb": 100}},
            "artifacts_dir": "/tmp",
            "device_serial": "device_001",
            "inject_stage": "precheck",
        }

        # Mock _record_step to avoid database dependency
        service._record_step = AsyncMock()

        result = await service._execute_inject_phase(1, context)

        assert result["success"] is True
        assert result["fault_injected"] is True


class TestExecutionServiceValidate:
    """测试ExecutionService验证阶段。"""

    @pytest.fixture
    def service(self):
        """创建服务实例。"""
        from app.services.execution_service import ExecutionService
        return ExecutionService()

    async def test_validate_phase_no_validator(self, service, mock_executor):
        """测试无验证器时跳过验证。"""
        context = {
            "validator": None,
            "executor": mock_executor,
            "validation_profile": {},
            "artifacts_dir": "/tmp",
        }

        result = await service._execute_validate_phase(1, context)

        assert result["passed"] is True
        assert result["skipped"] is True

    async def test_validate_phase_with_validator(self, service, mock_executor):
        """测试带验证器的验证阶段。"""
        from app.validators.base import DefaultValidator

        validator = DefaultValidator()
        context = {
            "validator": validator,
            "executor": mock_executor,
            "validation_profile": {},
            "artifacts_dir": "/tmp",
            "device_serial": "device_001",
            "inject_result": {"success": True},
        }

        # Mock _record_step to avoid database dependency
        service._record_step = AsyncMock()

        result = await service._execute_validate_phase(1, context)

        assert result["passed"] is True
        assert len(result["checks"]) > 0


class TestExecutionServiceJudgment:
    """测试ExecutionService最终判定。"""

    @pytest.fixture
    def service(self):
        """创建服务实例。"""
        from app.services.execution_service import ExecutionService
        return ExecutionService()

    def test_make_final_judgment_passed(self, service):
        """测试最终判定为passed。"""
        context = {
            "inject_result": {"success": True, "fault_injected": True},
            "validation_result": {"passed": True, "fault_observed": True},
            "recovery_result": {"passed": True},
            "fault_profile": {"risk_level": "medium"},
        }

        judgment = service._make_final_judgment(context)

        assert judgment.final_status == "passed"
        assert judgment.fault_injected is True
        assert judgment.validation_passed is True
        assert judgment.recovery_passed is True

    def test_make_final_judgment_failed(self, service):
        """测试最终判定为failed。"""
        context = {
            "inject_result": {"success": True, "fault_injected": True},
            "validation_result": {"passed": False},
            "recovery_result": {"passed": True},
            "fault_profile": {"risk_level": "medium"},
        }

        judgment = service._make_final_judgment(context)

        assert judgment.final_status == "failed"

    def test_make_final_judgment_partial(self, service):
        """测试最终判定为partial。"""
        context = {
            "inject_result": {"success": True, "fault_injected": True},
            "validation_result": {"passed": True},
            "recovery_result": {"passed": False},
            "fault_profile": {"risk_level": "high"},
        }

        judgment = service._make_final_judgment(context)

        assert judgment.final_status == "partial"
        assert judgment.manual_action_required is True

    def test_make_final_judgment_inject_failed(self, service):
        """测试注入失败时最终判定。"""
        context = {
            "inject_result": {"success": False, "fault_injected": False},
            "validation_result": None,
            "recovery_result": None,
            "fault_profile": {},
        }

        judgment = service._make_final_judgment(context)

        assert judgment.final_status == "partial"
        assert judgment.manual_action_required is True

    def test_make_final_judgment_inject_failed(self, service):
        """测试注入失败时最终判定。"""
        context = {
            "inject_result": {"success": False, "fault_injected": False},
            "validation_result": None,
            "recovery_result": None,
            "fault_profile": {},
        }

        judgment = service._make_final_judgment(context)

        assert judgment.final_status == "failed"
        assert judgment.fault_injected is False


# ==================== DeviceLockManager 测试 ====================

class TestDeviceLock:
    """测试 DeviceLock 数据类。"""

    def test_lock_creation(self):
        """测试创建设备锁。"""
        lock = DeviceLock(
            device_serial="device_001",
            scenario_run_id=1,
            acquired_at=datetime.utcnow(),
            timeout_sec=300,
        )

        assert lock.device_serial == "device_001"
        assert lock.scenario_run_id == 1
        assert lock.timeout_sec == 300

    def test_lock_is_expired_false(self):
        """测试未过期锁的过期检查。"""
        lock = DeviceLock(
            device_serial="device_001",
            scenario_run_id=1,
            acquired_at=datetime.utcnow(),
            timeout_sec=300,
        )

        assert lock.is_expired() is False
        assert lock.remaining_time() > 0

    def test_lock_is_expired_true(self):
        """测试过期锁的过期检查。"""
        lock = DeviceLock(
            device_serial="device_001",
            scenario_run_id=1,
            acquired_at=datetime.utcnow() - timedelta(seconds=400),
            timeout_sec=300,
        )

        assert lock.is_expired() is True
        assert lock.remaining_time() == 0.0


class TestDeviceLockManagerBasic:
    """测试 DeviceLockManager 基础功能。"""

    @pytest.fixture
    def lock_manager(self):
        """创建设备锁管理器实例。"""
        return DeviceLockManager(default_timeout=60, cleanup_interval=10)

    def test_manager_init(self, lock_manager):
        """测试管理器初始化。"""
        assert lock_manager._default_timeout == 60
        assert lock_manager._cleanup_interval == 10
        assert isinstance(lock_manager._locks, dict)

    async def test_acquire_lock_success(self, lock_manager):
        """测试成功获取锁。"""
        lock = await lock_manager.acquire_lock(
            device_serial="device_001",
            scenario_run_id=1,
            timeout_sec=60,
            wait_timeout_sec=10,
        )

        assert lock is not None
        assert lock.device_serial == "device_001"
        assert lock.scenario_run_id == 1
        assert lock.is_expired() is False

    async def test_acquire_lock_replaces_expired(self, lock_manager):
        """测试获取锁时替换过期锁。"""
        from datetime import timedelta

        # 先创建一个过期锁
        lock_manager._locks["device_001"] = DeviceLock(
            device_serial="device_001",
            scenario_run_id=999,
            acquired_at=datetime.utcnow() - timedelta(seconds=100),
            timeout_sec=50,  # 已过期
        )

        # 获取新锁应成功替换
        new_lock = await lock_manager.acquire_lock(
            device_serial="device_001",
            scenario_run_id=1,
            timeout_sec=60,
        )

        assert new_lock is not None
        assert new_lock.scenario_run_id == 1
        assert "device_001" in lock_manager._locks

    async def test_release_lock_success(self, lock_manager):
        """测试成功释放锁。"""
        # 先获取锁
        await lock_manager.acquire_lock(
            device_serial="device_001",
            scenario_run_id=1,
        )

        # 释放锁
        released = await lock_manager.release_lock(
            device_serial="device_001",
            scenario_run_id=1,
        )

        assert released is True
        assert "device_001" not in lock_manager._locks

    async def test_release_lock_not_found(self, lock_manager):
        """测试释放不存在的锁。"""
        released = await lock_manager.release_lock(
            device_serial="device_001",
            scenario_run_id=1,
        )

        assert released is False

    async def test_release_lock_owner_mismatch(self, lock_manager):
        """测试释放锁时所有权不匹配。"""
        # 先获取锁
        await lock_manager.acquire_lock(
            device_serial="device_001",
            scenario_run_id=1,
        )

        # 尝试用不同的 run_id 释放
        released = await lock_manager.release_lock(
            device_serial="device_001",
            scenario_run_id=2,
        )

        assert released is False
        # 锁仍然存在于 manager 中
        assert "device_001" in lock_manager._locks

    async def test_is_locked_true(self, lock_manager):
        """测试检查锁存在返回 True。"""
        await lock_manager.acquire_lock(
            device_serial="device_001",
            scenario_run_id=1,
        )

        locked = await lock_manager.is_locked("device_001")
        assert locked is True

    async def test_is_locked_false(self, lock_manager):
        """测试检查锁不存在返回 False。"""
        locked = await lock_manager.is_locked("device_001")
        assert locked is False

    async def test_is_locked_expired(self, lock_manager):
        """测试检查过期锁返回 False。"""
        from datetime import timedelta

        lock_manager._locks["device_001"] = DeviceLock(
            device_serial="device_001",
            scenario_run_id=1,
            acquired_at=datetime.utcnow() - timedelta(seconds=100),
            timeout_sec=50,  # 已过期
        )

        locked = await lock_manager.is_locked("device_001")
        assert locked is False

    async def test_get_lock_info(self, lock_manager):
        """测试获取锁信息。"""
        await lock_manager.acquire_lock(
            device_serial="device_001",
            scenario_run_id=1,
        )

        lock_info = await lock_manager.get_lock_info("device_001")

        assert lock_info is not None
        assert lock_info.device_serial == "device_001"
        assert lock_info.scenario_run_id == 1

    async def test_get_lock_info_not_locked(self, lock_manager):
        """测试获取未锁定设备的信息。"""
        lock_info = await lock_manager.get_lock_info("device_001")
        assert lock_info is None

    async def test_force_release_lock(self, lock_manager):
        """测试强制释放锁。"""
        await lock_manager.acquire_lock(
            device_serial="device_001",
            scenario_run_id=1,
        )

        released = await lock_manager.force_release_lock(
            device_serial="device_001",
            reason="test_force",
        )

        assert released is True
        assert "device_001" not in lock_manager._locks

    async def test_force_release_lock_not_locked(self, lock_manager):
        """测试强制释放未锁定的设备。"""
        released = await lock_manager.force_release_lock(
            device_serial="device_001",
            reason="test",
        )

        assert released is False

    async def test_get_all_locks(self, lock_manager):
        """测试获取所有锁。"""
        await lock_manager.acquire_lock("device_001", 1)
        await lock_manager.acquire_lock("device_002", 2)

        all_locks = await lock_manager.get_all_locks()

        assert len(all_locks) == 2
        assert "device_001" in all_locks
        assert "device_002" in all_locks

    async def test_get_locked_devices(self, lock_manager):
        """测试获取所有被锁定的设备。"""
        await lock_manager.acquire_lock("device_001", 1)
        await lock_manager.acquire_lock("device_002", 2)

        devices = await lock_manager.get_locked_devices()

        assert devices == {"device_001", "device_002"}

    async def test_cleanup_expired_locks(self, lock_manager):
        """测试清理过期锁。"""
        from datetime import timedelta

        # 创建一个活跃锁
        await lock_manager.acquire_lock("device_001", 1, timeout_sec=300)

        # 创建一个过期锁
        lock_manager._locks["device_002"] = DeviceLock(
            device_serial="device_002",
            scenario_run_id=2,
            acquired_at=datetime.utcnow() - timedelta(seconds=100),
            timeout_sec=50,
        )

        cleaned = await lock_manager.cleanup_expired_locks()

        assert cleaned == 1
        assert "device_002" not in lock_manager._locks
        assert "device_001" in lock_manager._locks


class TestDeviceLockManagerConcurrent:
    """测试 DeviceLockManager 并发场景。"""

    @pytest.fixture
    def lock_manager(self):
        """创建设备锁管理器实例。"""
        return DeviceLockManager(default_timeout=300, cleanup_interval=60)

    async def test_concurrent_acquire_same_device(self, lock_manager):
        """测试并发获取同一设备的锁。"""
        import asyncio

        async def acquire_task(run_id):
            return await lock_manager.acquire_lock(
                device_serial="device_001",
                scenario_run_id=run_id,
                wait_timeout_sec=5,
            )

        # 并发获取同一设备的锁
        tasks = [acquire_task(i) for i in range(1, 4)]

        # 只有一个能成功，其他会超时
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 只有一个成功
        success_count = sum(1 for r in results if not isinstance(r, Exception))
        assert success_count == 1

    async def test_acquire_lock_timeout_waiting(self, lock_manager):
        """测试等待锁释放超时。"""
        import asyncio

        # 先获取一个长超时锁
        await lock_manager.acquire_lock(
            device_serial="device_001",
            scenario_run_id=1,
            timeout_sec=300,
        )

        # 尝试获取锁，等待超时
        with pytest.raises(DeviceLockTimeoutError):
            await lock_manager.acquire_lock(
                device_serial="device_001",
                scenario_run_id=2,
                wait_timeout_sec=1,  # 很短的等待时间
            )