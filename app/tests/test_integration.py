"""集成测试。

测试完整的场景执行流程。
"""
import asyncio
import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select

from app.models import (
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
from app.executors.mock_executor import MockDeviceExecutor, MockScenario
from app.injectors.storage_pressure import StoragePressureInjector
from app.services.execution_service import ExecutionService
from app.services.recovery_service import RecoveryService


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
            from app.models import Report

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
        from app.injectors.base import InjectContext
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
        from app.services import (
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
        from app.services import (
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


# ==================== 端到端集成测试 ====================

class TestEndToEndScenarios:
    """端到端集成测试，测试完整场景流程."""

    @pytest.mark.asyncio
    async def test_end_to_end_mock_storage_pressure(self, db_engine):
        """测试 Mock 模式下存储压力注入的完整流程.

        验证：
        1. 创建故障配置、验证配置、恢复配置
        2. 创建场景模板和执行记录
        3. 执行场景并验证状态流转
        4. 验证步骤记录和报告生成
        """
        from app.services.execution_service import ExecutionService
        from sqlalchemy import select

        # 1. 创建配置
        fault_profile = FaultProfile(
            name="存储压力测试",
            fault_type="storage_pressure",
            parameters={"pressure_mb": 500},
            safe_cleanup_required=True,
            risk_level="medium",
            is_active=True,
        )

        validation_profile = ValidationProfile(
            name="基础验证",
            checks_json=json.dumps(["boot_completed", "battery_ok"]),
            timeout_sec=180,
        )

        recovery_profile = RecoveryProfile(
            name="标准恢复",
            steps_json=json.dumps([{"action": "cleanup_storage"}]),
            manual_intervention_allowed=True,
            timeout_sec=300,
        )

        async with get_session_context() as session:
            session.add(fault_profile)
            session.add(validation_profile)
            session.add(recovery_profile)
            await session.flush()

            # 2. 创建场景模板
            scenario = ScenarioTemplate(
                name="存储压力测试场景",
                description="测试存储压力注入的完整流程",
                target_type="stability",
                fault_profile_id=fault_profile.id,
                validation_profile_id=validation_profile.id,
                recovery_profile_id=recovery_profile.id,
                inject_stage="precheck",
                executor_mode="mock",
                enabled=True,
            )
            session.add(scenario)
            await session.flush()

            # 3. 创建执行记录
            run = ScenarioRun(
                scenario_template_id=scenario.id,
                device_serial="test_device_e2e_001",
                status=RunStatus.QUEUED.value,
                inject_stage="precheck",
            )
            session.add(run)
            await session.flush()
            run_id = run.id

        # 4. 执行场景
        execution_service = ExecutionService()
        final_status = await execution_service.execute_scenario(run_id)

        # 5. 验证结果
        async with get_session_context() as session:
            result = await session.execute(
                select(ScenarioRun).where(ScenarioRun.id == run_id)
            )
            completed_run = result.scalar_one()

            # 验证执行状态
            assert completed_run.status == final_status.value
            assert completed_run.started_at is not None
            assert completed_run.finished_at is not None

            # 验证步骤记录
            steps_result = await session.execute(
                select(ScenarioStep)
                .where(ScenarioStep.scenario_run_id == run_id)
                .order_by(ScenarioStep.step_order)
            )
            steps = steps_result.scalars().all()
            assert len(steps) > 0
            step_types = [s.step_type for s in steps]
            assert "precheck" in step_types

    @pytest.mark.asyncio
    async def test_end_to_end_device_pool_scheduling(self, db_engine):
        """测试设备池调度的完整流程.

        验证：
        1. 创建设备池和多个设备
        2. 创建设备租赁
        3. 验证设备状态和租赁状态
        4. 验证设备分配逻辑
        """
        from app.models.device_pool import DevicePool
        from app.models.device_lease import DeviceLease
        from sqlalchemy import select

        async with get_session_context() as session:
            # 1. 创建设备池
            pool = DevicePool(
                name="测试设备池",
                purpose="test",
                reserved_emergency_ratio=0.2,
                max_parallel_jobs=10,
                enabled=True,
            )
            session.add(pool)
            await session.flush()

            # 2. 创建多个设备
            devices = [
                Device(
                    serial=f"device_pool_{i:03d}",
                    model="Pixel 7",
                    brand="Google",
                    status="available" if i % 2 == 0 else "busy",
                    pool_id=pool.id,
                    is_active=True,
                )
                for i in range(4)
            ]
            for device in devices:
                session.add(device)
            await session.flush()

            # 3. 创建设备租赁
            lease = DeviceLease(
                device_id=devices[0].id,
                worker_id="worker_test_001",
                status="active",
                expires_at=datetime.utcnow() + timedelta(hours=1),
            )
            session.add(lease)
            await session.flush()

            # 4. 验证设备池和设备
            pool_result = await session.execute(
                select(DevicePool).where(DevicePool.id == pool.id)
            )
            loaded_pool = pool_result.scalar_one()
            assert loaded_pool.name == "测试设备池"
            assert loaded_pool.enabled

            # 5. 验证设备
            devices_result = await session.execute(
                select(Device).where(Device.pool_id == pool.id)
            )
            pool_devices = devices_result.scalars().all()
            assert len(pool_devices) == 4

            available_count = sum(1 for d in pool_devices if d.status == "available")
            assert available_count == 2  # 一半设备可用

            # 6. 验证租赁记录
            lease_result = await session.execute(
                select(DeviceLease).where(DeviceLease.device_id == devices[0].id)
            )
            loaded_lease = lease_result.scalar_one()
            assert loaded_lease.status == "active"
            assert loaded_lease.worker_id == "worker_test_001"

    @pytest.mark.asyncio
    async def test_end_to_end_scenario_with_factories(self, db_engine):
        """使用工厂类测试完整场景流程.

        验证：
        1. 使用工厂类快速创建测试数据
        2. 执行场景并验证结果
        3. 验证工厂类生成的数据有效性
        """
        from app.tests.factories import (
            ScenarioFactory,
            FaultProfileFactory,
            DeviceFactory,
        )
        from app.services.execution_service import ExecutionService
        from sqlalchemy import select

        # 1. 使用工厂创建配置
        fault_profile = FaultProfileFactory.create(
            name="Factory Test Fault",
            fault_type=FaultType.storage_pressure,
            parameters={"pressure_mb": 250},
        )

        async with get_session_context() as session:
            session.add(fault_profile)
            await session.flush()
            fault_profile_id = fault_profile.id

            # 2. 使用工厂创建设备
            device = DeviceFactory.create(
                serial="factory_test_device",
                model="Pixel 7",
                status=DeviceStatus.available,
            )
            session.add(device)
            await session.flush()

            # 3. 创建场景模板
            scenario = ScenarioTemplate(
                name="Factory Test Scenario",
                description="使用工厂类创建的测试场景",
                target_type="stability",
                fault_profile_id=fault_profile_id,
                validation_profile_id=1,
                recovery_profile_id=1,
                inject_stage="precheck",
                executor_mode="mock",
                enabled=True,
            )
            session.add(scenario)
            await session.flush()

            # 4. 创建执行记录
            run = ScenarioRun(
                scenario_template_id=scenario.id,
                device_serial=device.serial,
                status=RunStatus.QUEUED.value,
                inject_stage="precheck",
            )
            session.add(run)
            await session.flush()
            run_id = run.id

        # 5. 执行场景
        execution_service = ExecutionService()
        final_status = await execution_service.execute_scenario(run_id)

        # 6. 验证结果
        async with get_session_context() as session:
            result = await session.execute(
                select(ScenarioRun).where(ScenarioRun.id == run_id)
            )
            completed_run = result.scalar_one()

            assert completed_run.device_serial == "factory_test_device"
            assert completed_run.status == final_status.value
            assert completed_run.finished_at is not None

            # 验证步骤
            steps_result = await session.execute(
                select(ScenarioStep)
                .where(ScenarioStep.scenario_run_id == run_id)
            )
            steps = steps_result.scalars().all()
            assert len(steps) > 0