"""
数据库模型单元测试。

测试所有数据库模型的创建、关系和枚举值。
"""
import json
from datetime import datetime

import pytest

from chaosdroid.models import (
    Artifact,
    ArtifactType,
    Base,
    ExecutorMode,
    FaultProfile,
    FaultType,
    InjectStage,
    Report,
    RecoveryProfile,
    RiskLevel,
    RunStatus,
    ScenarioRun,
    ScenarioStep,
    ScenarioTemplate,
    StepStatus,
    StepType,
    TargetType,
    ValidationProfile,
    create_tables,
    drop_tables,
    get_engine,
    get_session_context,
    init_engine,
    close_engine,
)


# ==================== Fixtures ====================

@pytest.fixture
async def db_engine():
    """创建内存数据库引擎。"""
    init_engine(":memory:")
    await create_tables()
    yield get_engine()
    await drop_tables()
    await close_engine()


@pytest.fixture
async def db_session(db_engine):
    """提供数据库会话。"""
    async with get_session_context() as session:
        yield session


@pytest.fixture
def fault_profile_data():
    """故障配置测试数据。"""
    return {
        "name": "存储压力测试",
        "fault_type": FaultType.storage_pressure.value,
        "parameters": {"pressure_mb": 1000, "target_path": "/sdcard/test"},
        "safe_cleanup_required": True,
        "risk_level": RiskLevel.medium.value,
        "is_active": True,
        "description": "测试存储压力注入",
    }


@pytest.fixture
def validation_profile_data():
    """验证配置测试数据。"""
    return {
        "name": "基础验证配置",
        "checks_json": json.dumps(["boot_completed", "battery_ok", "storage_ok"]),
        "timeout_sec": 180,
        "pass_rules_json": json.dumps({"all_checks_passed": True}),
        "description": "基础设备验证",
    }


@pytest.fixture
def recovery_profile_data():
    """恢复配置测试数据。"""
    return {
        "name": "标准恢复配置",
        "steps_json": json.dumps(["cleanup_storage", "check_online"]),
        "manual_intervention_allowed": True,
        "timeout_sec": 300,
        "description": "标准恢复流程",
    }


@pytest.fixture
async def fault_profile(db_session, fault_profile_data):
    """创建故障配置实例。"""
    profile = FaultProfile(**fault_profile_data)
    db_session.add(profile)
    await db_session.flush()
    return profile


@pytest.fixture
async def validation_profile(db_session, validation_profile_data):
    """创建验证配置实例。"""
    profile = ValidationProfile(**validation_profile_data)
    db_session.add(profile)
    await db_session.flush()
    return profile


@pytest.fixture
async def recovery_profile(db_session, recovery_profile_data):
    """创建恢复配置实例。"""
    profile = RecoveryProfile(**recovery_profile_data)
    db_session.add(profile)
    await db_session.flush()
    return profile


@pytest.fixture
async def scenario_template(db_session, fault_profile, validation_profile, recovery_profile):
    """创建场景模板实例。"""
    template = ScenarioTemplate(
        name="存储压力场景",
        description="测试存储压力注入和恢复",
        target_type=TargetType.STABILITY.value,
        fault_profile_id=fault_profile.id,
        inject_stage=InjectStage.PRECHECK.value,
        validation_profile_id=validation_profile.id,
        recovery_profile_id=recovery_profile.id,
        executor_mode=ExecutorMode.MOCK.value,
        enabled=True,
    )
    db_session.add(template)
    await db_session.flush()
    return template


@pytest.fixture
async def scenario_run(db_session, scenario_template):
    """创建场景执行记录实例。"""
    run = ScenarioRun(
        scenario_template_id=scenario_template.id,
        device_serial="mock_device_001",
        status=RunStatus.QUEUED.value,
        inject_stage=InjectStage.PRECHECK.value,
    )
    db_session.add(run)
    await db_session.flush()
    return run


# ==================== 枚举测试 ====================

class TestRunStatusEnum:
    """测试 RunStatus 枚举值。"""

    def test_all_status_values(self):
        """测试所有状态枚举值。"""
        expected_values = ["queued", "preparing", "injecting", "validating", "recovering", "passed", "failed", "partial"]
        actual_values = [status.value for status in RunStatus]
        assert actual_values == expected_values

    def test_queued_status(self):
        """测试排队状态。"""
        assert RunStatus.QUEUED.value == "queued"
        assert RunStatus.QUEUED == "queued"

    def test_final_status_values(self):
        """测试最终状态值。"""
        assert RunStatus.PASSED.value == "passed"
        assert RunStatus.FAILED.value == "failed"
        assert RunStatus.PARTIAL.value == "partial"


class TestFaultTypeEnum:
    """测试 FaultType 枚举值。"""

    def test_all_fault_types(self):
        """测试所有故障类型枚举值。"""
        expected_values = [
            "storage_pressure",
            "low_battery",
            "network_jitter",
            "reboot_timeout",
            "cpu_io_stress",
            "monkey_stability",
        ]
        actual_values = [fault.value for fault in FaultType]
        assert actual_values == expected_values

    def test_storage_pressure(self):
        """测试存储压力故障类型。"""
        assert FaultType.storage_pressure.value == "storage_pressure"

    def test_low_battery(self):
        """测试低电量故障类型。"""
        assert FaultType.low_battery.value == "low_battery"


class TestRiskLevelEnum:
    """测试 RiskLevel 枚举值。"""

    def test_all_risk_levels(self):
        """测试所有风险等级枚举值。"""
        expected_values = ["low", "medium", "high", "critical"]
        actual_values = [level.value for level in RiskLevel]
        assert actual_values == expected_values

    def test_risk_level_order(self):
        """测试风险等级顺序（从低到高）。"""
        assert RiskLevel.low.value == "low"
        assert RiskLevel.medium.value == "medium"
        assert RiskLevel.high.value == "high"
        assert RiskLevel.critical.value == "critical"


class TestInjectStageEnum:
    """测试 InjectStage 枚举值。"""

    def test_all_inject_stages(self):
        """测试所有注入阶段枚举值。"""
        expected_values = ["precheck", "prepare", "upgrading", "reboot_wait", "post_boot", "post_validate"]
        actual_values = [stage.value for stage in InjectStage]
        assert actual_values == expected_values


class TestExecutorModeEnum:
    """测试 ExecutorMode 枚举值。"""

    def test_executor_modes(self):
        """测试执行器模式枚举值。"""
        assert ExecutorMode.REAL.value == "real"
        assert ExecutorMode.MOCK.value == "mock"


class TestStepTypeEnum:
    """测试 StepType 枚举值。"""

    def test_all_step_types(self):
        """测试所有步骤类型枚举值。"""
        expected_values = ["precheck", "inject", "observe", "validate", "recover", "collect"]
        actual_values = [step.value for step in StepType]
        assert actual_values == expected_values


class TestStepStatusEnum:
    """测试 StepStatus 枚举值。"""

    def test_all_step_status(self):
        """测试所有步骤状态枚举值。"""
        expected_values = ["pending", "running", "success", "failed", "skipped", "timeout"]
        actual_values = [status.value for status in StepStatus]
        assert actual_values == expected_values


class TestArtifactTypeEnum:
    """测试 ArtifactType 枚举值。"""

    def test_all_artifact_types(self):
        """测试所有产物类型枚举值。"""
        expected_values = ["logcat", "getprop", "battery", "monkey", "stdout", "stderr", "snapshot", "summary", "other"]
        actual_values = [type.value for type in ArtifactType]
        assert actual_values == expected_values


# ==================== 模型创建测试 ====================

class TestFaultProfileCreation:
    """测试 FaultProfile 模型创建。"""

    async def test_create_fault_profile(self, db_session, fault_profile_data):
        """测试创建故障配置。"""
        profile = FaultProfile(**fault_profile_data)
        db_session.add(profile)
        await db_session.flush()

        assert profile.id is not None
        assert profile.name == fault_profile_data["name"]
        assert profile.fault_type == FaultType.storage_pressure.value
        assert profile.risk_level == RiskLevel.medium.value
        assert profile.safe_cleanup_required is True

    async def test_fault_profile_timestamps(self, db_session, fault_profile_data):
        """测试故障配置时间戳字段。"""
        profile = FaultProfile(**fault_profile_data)
        db_session.add(profile)
        await db_session.flush()

        assert profile.created_at is not None
        assert profile.updated_at is not None
        assert isinstance(profile.created_at, datetime)
        assert isinstance(profile.updated_at, datetime)

    async def test_fault_profile_default_values(self, db_session):
        """测试故障配置默认值。"""
        profile = FaultProfile(
            name="默认配置",
            fault_type=FaultType.cpu_io_stress.value,
        )
        db_session.add(profile)
        await db_session.flush()

        assert profile.safe_cleanup_required is False  # 默认不需要安全清理
        assert profile.risk_level == RiskLevel.low.value  # 默认低风险


class TestValidationProfileCreation:
    """测试 ValidationProfile 模型创建。"""

    async def test_create_validation_profile(self, db_session, validation_profile_data):
        """测试创建验证配置。"""
        profile = ValidationProfile(**validation_profile_data)
        db_session.add(profile)
        await db_session.flush()

        assert profile.id is not None
        assert profile.name == validation_profile_data["name"]
        assert profile.timeout_sec == 180

    async def test_validation_profile_default_timeout(self, db_session):
        """测试验证配置默认超时时间。"""
        profile = ValidationProfile(name="默认验证")
        db_session.add(profile)
        await db_session.flush()

        assert profile.timeout_sec == 180  # 默认180秒


class TestRecoveryProfileCreation:
    """测试 RecoveryProfile 模型创建。"""

    async def test_create_recovery_profile(self, db_session, recovery_profile_data):
        """测试创建恢复配置。"""
        profile = RecoveryProfile(**recovery_profile_data)
        db_session.add(profile)
        await db_session.flush()

        assert profile.id is not None
        assert profile.name == recovery_profile_data["name"]
        assert profile.manual_intervention_allowed is True
        assert profile.timeout_sec == 300

    async def test_recovery_profile_defaults(self, db_session):
        """测试恢复配置默认值。"""
        profile = RecoveryProfile(name="默认恢复")
        db_session.add(profile)
        await db_session.flush()

        assert profile.manual_intervention_allowed is True  # 默认允许人工介入
        assert profile.timeout_sec == 300  # 默认300秒


class TestScenarioTemplateCreation:
    """测试 ScenarioTemplate 模型创建。"""

    async def test_create_scenario_template(self, db_session, fault_profile, validation_profile, recovery_profile):
        """测试创建场景模板。"""
        template = ScenarioTemplate(
            name="测试场景",
            description="测试场景描述",
            target_type=TargetType.UPGRADE.value,
            fault_profile_id=fault_profile.id,
            inject_stage=InjectStage.UPGRADING.value,
            validation_profile_id=validation_profile.id,
            recovery_profile_id=recovery_profile.id,
            executor_mode=ExecutorMode.REAL.value,
            enabled=True,
        )
        db_session.add(template)
        await db_session.flush()

        assert template.id is not None
        assert template.name == "测试场景"
        assert template.target_type == TargetType.UPGRADE.value
        assert template.executor_mode == ExecutorMode.REAL.value

    async def test_scenario_template_defaults(self, db_session):
        """测试场景模板默认值。"""
        template = ScenarioTemplate(name="默认场景")
        db_session.add(template)
        await db_session.flush()

        assert template.target_type == TargetType.STABILITY.value  # 默认稳定性测试
        assert template.inject_stage == InjectStage.PRECHECK.value  # 默认前置检查阶段
        assert template.executor_mode == ExecutorMode.MOCK.value  # 默认Mock模式
        assert template.enabled is True  # 默认启用


class TestScenarioRunCreation:
    """测试 ScenarioRun 模型创建。"""

    async def test_create_scenario_run(self, scenario_run):
        """测试创建场景执行记录。"""
        assert scenario_run.id is not None
        assert scenario_run.device_serial == "mock_device_001"
        assert scenario_run.status == RunStatus.QUEUED.value

    async def test_scenario_run_defaults(self, db_session):
        """测试场景执行记录默认值。"""
        run = ScenarioRun(device_serial="device_001")
        db_session.add(run)
        await db_session.flush()

        assert run.status == RunStatus.QUEUED.value  # 默认排队状态
        assert run.inject_stage == InjectStage.PRECHECK.value  # 默认前置检查阶段

    async def test_scenario_run_started_finished_times(self, db_session, scenario_template):
        """测试场景执行记录时间字段。"""
        run = ScenarioRun(
            scenario_template_id=scenario_template.id,
            device_serial="device_002",
            status=RunStatus.PREPARING.value,
            started_at=datetime.utcnow(),
        )
        db_session.add(run)
        await db_session.flush()

        assert run.started_at is not None
        assert run.finished_at is None  # 未完成时为空


class TestScenarioStepCreation:
    """测试 ScenarioStep 模型创建。"""

    async def test_create_scenario_step(self, db_session, scenario_run):
        """测试创建执行步骤记录。"""
        step = ScenarioStep(
            scenario_run_id=scenario_run.id,
            step_type=StepType.PRECHECK.value,
            step_order=1,
            status=StepStatus.RUNNING.value,
            started_at=datetime.utcnow(),
        )
        db_session.add(step)
        await db_session.flush()

        assert step.id is not None
        assert step.step_type == StepType.PRECHECK.value
        assert step.step_order == 1
        assert step.status == StepStatus.RUNNING.value

    async def test_scenario_step_defaults(self, db_session, scenario_run):
        """测试步骤记录默认值。"""
        step = ScenarioStep(
            scenario_run_id=scenario_run.id,
            step_type=StepType.INJECT.value,
            step_order=2,
        )
        db_session.add(step)
        await db_session.flush()

        assert step.status == StepStatus.PENDING.value  # 默认待执行


class TestArtifactCreation:
    """测试 Artifact 模型创建。"""

    async def test_create_artifact(self, db_session, scenario_run):
        """测试创建执行产物记录。"""
        artifact = Artifact(
            scenario_run_id=scenario_run.id,
            artifact_type=ArtifactType.LOGCAT.value,
            path="artifacts/1/logcat.txt",
            size=1024,
            meta_json=json.dumps({"lines": 1000}),
        )
        db_session.add(artifact)
        await db_session.flush()

        assert artifact.id is not None
        assert artifact.artifact_type == ArtifactType.LOGCAT.value
        assert artifact.path == "artifacts/1/logcat.txt"
        assert artifact.size == 1024


class TestReportCreation:
    """测试 Report 模型创建。"""

    async def test_create_report(self, db_session, scenario_run):
        """测试创建报告记录。"""
        report = Report(
            scenario_run_id=scenario_run.id,
            markdown_path="reports/1/report.md",
            html_path="reports/1/report.html",
            summary_json=json.dumps({"status": "passed"}),
        )
        db_session.add(report)
        await db_session.flush()

        assert report.id is not None
        assert report.scenario_run_id == scenario_run.id
        assert report.markdown_path is not None


# ==================== 模型关系测试 ====================

class TestModelRelationships:
    """测试模型之间的关系。"""

    async def test_scenario_template_profile_relationships(
        self, scenario_template, fault_profile, validation_profile, recovery_profile
    ):
        """测试场景模板与配置的关系。"""
        assert scenario_template.fault_profile_id == fault_profile.id
        assert scenario_template.validation_profile_id == validation_profile.id
        assert scenario_template.recovery_profile_id == recovery_profile.id

    async def test_scenario_run_template_relationship(self, scenario_run, scenario_template):
        """测试执行记录与场景模板的关系。"""
        assert scenario_run.scenario_template_id == scenario_template.id

    async def test_scenario_step_run_relationship(self, db_session, scenario_run):
        """测试步骤记录与执行记录的关系。"""
        step1 = ScenarioStep(
            scenario_run_id=scenario_run.id,
            step_type=StepType.PRECHECK.value,
            step_order=1,
        )
        step2 = ScenarioStep(
            scenario_run_id=scenario_run.id,
            step_type=StepType.INJECT.value,
            step_order=2,
        )
        db_session.add_all([step1, step2])
        await db_session.flush()

        # 验证步骤关联到同一个执行记录
        assert step1.scenario_run_id == scenario_run.id
        assert step2.scenario_run_id == scenario_run.id

    async def test_artifact_relationships(self, db_session, scenario_run):
        """测试产物与执行记录、步骤的关系。"""
        step = ScenarioStep(
            scenario_run_id=scenario_run.id,
            step_type=StepType.COLLECT.value,
            step_order=5,
        )
        db_session.add(step)
        await db_session.flush()

        artifact = Artifact(
            scenario_run_id=scenario_run.id,
            step_id=step.id,
            artifact_type=ArtifactType.SNAPSHOT.value,
            path="artifacts/1/snapshot.json",
        )
        db_session.add(artifact)
        await db_session.flush()

        assert artifact.scenario_run_id == scenario_run.id
        assert artifact.step_id == step.id

    async def test_report_run_relationship(self, db_session, scenario_run):
        """测试报告与执行记录的一对一关系。"""
        report = Report(scenario_run_id=scenario_run.id)
        db_session.add(report)
        await db_session.flush()

        assert report.scenario_run_id == scenario_run.id


# ==================== JSON字段测试 ====================

class TestJSONFieldHandling:
    """测试 JSON 字段的存储和读取。"""

    async def test_fault_profile_parameters(self, db_session):
        """测试故障配置参数JSON字段。"""
        params = {
            "pressure_mb": 500,
            "target_path": "/data/local/tmp",
            "chunk_size": 50,
        }
        profile = FaultProfile(
            name="JSON测试",
            fault_type=FaultType.storage_pressure.value,
            parameters=params,
        )
        db_session.add(profile)
        await db_session.flush()

        # 直接读取JSON字段，无需手动解析
        assert profile.parameters["pressure_mb"] == 500
        assert profile.parameters["target_path"] == "/data/local/tmp"

    async def test_validation_profile_checks_json(self, db_session):
        """测试验证配置检查项JSON字段。"""
        checks = ["boot_completed", "battery_level", "storage_available", "device_online"]
        profile = ValidationProfile(
            name="验证JSON测试",
            checks_json=json.dumps(checks),
            pass_rules_json=json.dumps({"min_battery": 20}),
        )
        db_session.add(profile)
        await db_session.flush()

        loaded_checks = json.loads(profile.checks_json)
        assert len(loaded_checks) == 4
        assert "boot_completed" in loaded_checks

    async def test_scenario_run_result_summary_json(self, db_session):
        """测试执行记录结果摘要JSON字段。"""
        summary = {
            "inject_result": {"success": True, "pressure_mb": 1000},
            "validation_result": {"passed": True, "checks_count": 4},
            "recovery_result": {"cleanup_success": True},
        }
        run = ScenarioRun(
            device_serial="json_test_device",
            result_summary_json=json.dumps(summary),
        )
        db_session.add(run)
        await db_session.flush()

        loaded_summary = json.loads(run.result_summary_json)
        assert loaded_summary["inject_result"]["success"] is True

    async def test_scenario_step_summary_json(self, db_session, scenario_run):
        """测试步骤记录摘要JSON字段。"""
        summary = {
            "duration_ms": 1500,
            "output": "命令执行成功",
            "error": None,
        }
        step = ScenarioStep(
            scenario_run_id=scenario_run.id,
            step_type=StepType.INJECT.value,
            step_order=1,
            summary_json=json.dumps(summary),
        )
        db_session.add(step)
        await db_session.flush()

        loaded_summary = json.loads(step.summary_json)
        assert loaded_summary["duration_ms"] == 1500

    async def test_artifact_meta_json(self, db_session, scenario_run):
        """测试产物元数据JSON字段。"""
        meta = {
            "created_at": datetime.utcnow().isoformat(),
            "format": "text",
            "encoding": "utf-8",
        }
        artifact = Artifact(
            scenario_run_id=scenario_run.id,
            artifact_type=ArtifactType.STDOUT.value,
            path="artifacts/stdout.log",
            meta_json=json.dumps(meta),
        )
        db_session.add(artifact)
        await db_session.flush()

        loaded_meta = json.loads(artifact.meta_json)
        assert loaded_meta["format"] == "text"

    async def test_null_json_fields(self, db_session):
        """测试JSON字段为空值的情况。"""
        profile = FaultProfile(
            name="空JSON测试",
            fault_type=FaultType.network_jitter.value,
            parameters=None,
        )
        db_session.add(profile)
        await db_session.flush()

        assert profile.parameters is None


# ==================== 模型字符串表示测试 ====================

class TestModelRepr:
    """测试模型的字符串表示方法。"""

    async def test_fault_profile_repr(self, fault_profile):
        """测试故障配置的字符串表示。"""
        repr_str = repr(fault_profile)
        assert "FaultProfile" in repr_str
        assert str(fault_profile.id) in repr_str
        assert fault_profile.name in repr_str

    async def test_scenario_template_repr(self, scenario_template):
        """测试场景模板的字符串表示。"""
        repr_str = repr(scenario_template)
        assert "ScenarioTemplate" in repr_str
        assert str(scenario_template.id) in repr_str
        assert scenario_template.name in repr_str

    async def test_scenario_run_repr(self, scenario_run):
        """测试执行记录的字符串表示。"""
        repr_str = repr(scenario_run)
        assert "ScenarioRun" in repr_str
        assert str(scenario_run.id) in repr_str
        assert scenario_run.device_serial in repr_str

    async def test_scenario_step_repr(self, db_session, scenario_run):
        """测试步骤记录的字符串表示。"""
        step = ScenarioStep(
            scenario_run_id=scenario_run.id,
            step_type=StepType.VALIDATE.value,
            step_order=3,
        )
        db_session.add(step)
        await db_session.flush()

        repr_str = repr(step)
        assert "ScenarioStep" in repr_str
        assert step.step_type in repr_str

    async def test_artifact_repr(self, db_session, scenario_run):
        """测试产物记录的字符串表示。"""
        artifact = Artifact(
            scenario_run_id=scenario_run.id,
            artifact_type=ArtifactType.MONKEY.value,
            path="test.txt",
        )
        db_session.add(artifact)
        await db_session.flush()

        repr_str = repr(artifact)
        assert "Artifact" in repr_str
        assert artifact.artifact_type in repr_str