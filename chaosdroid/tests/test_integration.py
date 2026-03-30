"""集成测试。

测试完整的场景执行流程。
"""
import asyncio
import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select

from chaosdroid.models import (
    FaultProfile,
    ValidationProfile,
    RecoveryProfile,
    ScenarioTemplate,
    ScenarioRun,
    ScenarioStep,
    RunStatus,
    StepStatus,
    init_engine,
    create_tables,
    drop_tables,
    close_engine,
    get_session_context,
)
from chaosdroid.executors.mock_executor import MockDeviceExecutor, MockScenario
from chaosdroid.injectors.storage_pressure import StoragePressureInjector
from chaosdroid.services.execution_service import ExecutionService
from chaosdroid.services.recovery_service import RecoveryService


# ==================== Fixtures ====================

@pytest.fixture
async def db_engine():
    """创建内存数据库引擎。"""
    init_engine(":memory:")
    await create_tables()
    yield
    await drop_tables()
    await close_engine()


@pytest.fixture
async def db_session(db_engine):
    """提供数据库会话。"""
    async with get_session_context() as session:
        yield session


@pytest.fixture
async def sample_profiles(db_session):
    """创建示例配置。"""
    # 故障配置
    fault_profile = FaultProfile(
        name="存储压力测试",
        fault_type="storage_pressure",
        parameters={"pressure_mb": 500, "target_path": "/sdcard/test"},
        safe_cleanup_required=True,
        risk_level="medium",
        is_active=True,
    )
    db_session.add(fault_profile)
    await db_session.flush()

    # 验证配置
    validation_profile = ValidationProfile(
        name="基础验证",
        checks_json=json.dumps(["boot_completed", "battery_ok"]),
        timeout_sec=180,
    )
    db_session.add(validation_profile)
    await db_session.flush()

    # 恢复配置
    recovery_profile = RecoveryProfile(
        name="标准恢复",
        steps_json=json.dumps([{"action": "cleanup_storage"}]),
        manual_intervention_allowed=True,
        timeout_sec=300,
    )
    db_session.add(recovery_profile)
    await db_session.flush()

    return {
        "fault": fault_profile,
        "validation": validation_profile,
        "recovery": recovery_profile,
    }


@pytest.fixture
async def sample_scenario(db_session, sample_profiles):
    """创建示例场景模板。"""
    scenario = ScenarioTemplate(
        name="测试场景",
        description="集成测试场景",
        target_type="stability",
        fault_profile_id=sample_profiles["fault"].id,
        validation_profile_id=sample_profiles["validation"].id,
        recovery_profile_id=sample_profiles["recovery"].id,
        inject_stage="precheck",
        executor_mode="mock",
        enabled=True,
    )
    db_session.add(scenario)
    await db_session.flush()
    return scenario


@pytest.fixture
async def sample_run(db_session, sample_scenario):
    """创建示例执行记录。"""
    run = ScenarioRun(
        scenario_template_id=sample_scenario.id,
        device_serial="test_device_001",
        status=RunStatus.QUEUED.value,
        inject_stage="precheck",
    )
    db_session.add(run)
    await db_session.flush()
    return run


# ==================== 集成测试 ====================

class TestExecutionFlow:
    """测试完整执行流程。"""

    @pytest.mark.asyncio
    async def test_mock_execution_flow(self, db_engine, sample_run):
        """测试Mock模式完整执行流程。"""
        execution_service = ExecutionService()

        # 执行场景
        final_status = await execution_service.execute_scenario(sample_run.id)

        # 验证最终状态
        assert final_status in [RunStatus.PASSED, RunStatus.FAILED, RunStatus.PARTIAL]

        # 验证数据库记录
        async with get_session_context() as session:
            result = await session.execute(
                select(ScenarioRun).where(ScenarioRun.id == sample_run.id)
            )
            run = result.scalar_one()
            assert run.status == final_status.value
            assert run.started_at is not None
            assert run.finished_at is not None

    @pytest.mark.asyncio
    async def test_step_recording(self, db_engine, sample_run):
        """测试步骤记录。"""
        execution_service = ExecutionService()

        # 执行场景
        await execution_service.execute_scenario(sample_run.id)

        # 验证步骤记录
        async with get_session_context() as session:
            result = await session.execute(
                select(ScenarioStep)
                .where(ScenarioStep.scenario_run_id == sample_run.id)
                .order_by(ScenarioStep.step_order)
            )
            steps = result.scalars().all()

            assert len(steps) > 0
            # 验证步骤类型
            step_types = [s.step_type for s in steps]
            assert "precheck" in step_types

    @pytest.mark.asyncio
    async def test_report_generation(self, db_engine, sample_run):
        """测试报告生成。"""
        execution_service = ExecutionService()

        # 执行场景
        await execution_service.execute_scenario(sample_run.id)

        # 验证报告生成
        async with get_session_context() as session:
            from chaosdroid.models import Report

            result = await session.execute(
                select(Report).where(Report.scenario_run_id == sample_run.id)
            )
            report = result.scalar_one_or_none()

            # 如果执行完成，应该有报告
            if report:
                assert report.markdown_path is not None or report.summary_json is not None


class TestMockDeviceScenarios:
    """测试Mock设备不同场景。"""

    @pytest.mark.asyncio
    async def test_normal_device(self):
        """测试正常设备执行。"""
        executor = MockDeviceExecutor("normal_device", MockScenario.normal)

        # 验证设备状态
        assert await executor.is_online()
        assert await executor.check_boot_completed()

        # 获取设备信息
        battery = await executor.get_battery_info()
        assert battery.level == 100

        storage = await executor.get_storage_info()
        assert storage.available > 0

    @pytest.mark.asyncio
    async def test_offline_device(self):
        """测试离线设备。"""
        executor = MockDeviceExecutor("offline_device", MockScenario.offline)

        # 验证设备离线
        assert not await executor.is_online()

    @pytest.mark.asyncio
    async def test_low_battery_device(self):
        """测试低电量设备。"""
        executor = MockDeviceExecutor("low_battery_device", MockScenario.low_battery)

        # 验证低电量
        battery = await executor.get_battery_info()
        assert battery.level < 20

    @pytest.mark.asyncio
    async def test_storage_full_device(self):
        """测试存储满设备。"""
        executor = MockDeviceExecutor("storage_full_device", MockScenario.storage_full)

        # 验证存储不足
        storage = await executor.get_storage_info()
        assert storage.available < 100 * 1024 * 1024  # < 100MB

    @pytest.mark.asyncio
    async def test_boot_timeout_device(self):
        """测试启动超时设备。"""
        executor = MockDeviceExecutor("boot_timeout_device", MockScenario.boot_timeout)

        # 验证boot未完成
        assert not await executor.check_boot_completed()


class TestInjectorFlow:
    """测试注入器流程。"""

    @pytest.mark.asyncio
    async def test_storage_pressure_injector(self):
        """测试存储压力注入器完整流程。"""
        from chaosdroid.injectors.base import InjectContext
        from datetime import datetime

        executor = MockDeviceExecutor("test_device", MockScenario.normal)
        injector = StoragePressureInjector()

        # 准备上下文
        context = InjectContext(
            scenario_run_id=1,
            device_serial="test_device",
            executor=executor,
            fault_profile={
                "parameters": {"pressure_mb": 500}
            },
            artifacts_dir="/tmp/test",
            started_at=datetime.utcnow(),
            inject_stage="precheck",
        )

        # 准备
        prepare_result = await injector.prepare(context)
        assert prepare_result

        # 注入
        inject_result = await injector.inject(context)
        assert inject_result.success
        assert inject_result.fault_injected

        # 清理
        cleanup_result = await injector.cleanup(context)
        assert cleanup_result


class TestRecoveryService:
    """测试恢复服务。"""

    @pytest.mark.asyncio
    async def test_recovery_service_basic(self):
        """测试恢复服务基本功能。"""
        recovery_profile = {
            "steps": [
                {"name": "cleanup", "action": "cleanup_storage", "required": True},
                {"name": "verify", "action": "check_connectivity", "required": True},
            ],
            "manual_intervention_allowed": True,
        }

        recovery_service = RecoveryService(recovery_profile)
        executor = MockDeviceExecutor("test_device", MockScenario.normal)

        # 执行恢复
        context = {"injector": None, "scenario_run_id": 1}
        result = await recovery_service.execute_recovery_steps(executor, context)

        # 返回的是字典格式
        assert result["passed"]
        assert len(result["steps"]) > 0


class TestAPIEndpoints:
    """测试API端点。"""

    @pytest.mark.asyncio
    async def test_scenario_crud(self, db_engine, sample_scenario):
        """测试场景CRUD操作。"""
        from chaosdroid.services import (
            get_scenario,
            list_scenarios,
            ScenarioFilters,
        )

        # 读取
        scenario = await get_scenario(sample_scenario.id)
        assert scenario is not None
        assert scenario.name == "测试场景"

        # 列表
        scenarios = await list_scenarios(ScenarioFilters())
        assert len(scenarios) > 0

    @pytest.mark.asyncio
    async def test_run_crud(self, db_engine, sample_run):
        """测试执行记录CRUD操作。"""
        from chaosdroid.services import (
            get_run,
            list_runs,
            RunFilters,
        )

        # 读取
        run = await get_run(sample_run.id)
        assert run is not None
        assert run.device_serial == "test_device_001"

        # 列表
        runs = await list_runs(RunFilters())
        assert len(runs) > 0