"""
注入器单元测试。

测试注入器基类、注册机制和StoragePressureInjector。
"""
import asyncio
import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from chaosdroid.injectors.base import (
    BaseInjector,
    FaultType,
    RiskLevel,
    InjectContext,
    InjectResult,
    INJECTOR_REGISTRY,
    register_injector,
    get_injector,
    list_injectors,
)
from chaosdroid.injectors.storage_pressure import StoragePressureInjector
from chaosdroid.executors.mock_executor import MockDeviceExecutor, MockDeviceState, MockScenario
from chaosdroid.executors.base import StorageInfo, BatteryInfo, ShellResult


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
def mock_executor_storage_full():
    """创建存储满Mock设备执行器。"""
    return MockDeviceExecutor("storage_full_device", MockScenario.storage_full)


@pytest.fixture
def inject_context(mock_executor):
    """创建注入上下文。"""
    return InjectContext(
        scenario_run_id=1,
        device_serial="test_device_001",
        executor=mock_executor,
        fault_profile={
            "parameters": {
                "pressure_mb": 500,
                "target_path": "/sdcard/test_pressure",
            }
        },
        artifacts_dir="/tmp/artifacts",
        started_at=datetime.utcnow(),
        inject_stage="precheck",
    )


@pytest.fixture
def inject_context_offline(mock_executor_offline):
    """创建离线设备的注入上下文。"""
    return InjectContext(
        scenario_run_id=2,
        device_serial="offline_device",
        executor=mock_executor_offline,
        fault_profile={"parameters": {"pressure_mb": 500}},
        artifacts_dir="/tmp/artifacts",
    )


@pytest.fixture
def inject_context_storage_full(mock_executor_storage_full):
    """创建存储满设备的注入上下文。"""
    return InjectContext(
        scenario_run_id=3,
        device_serial="storage_full_device",
        executor=mock_executor_storage_full,
        fault_profile={"parameters": {"pressure_mb": 500}},
        artifacts_dir="/tmp/artifacts",
    )


@pytest.fixture
def storage_injector():
    """创建存储压力注入器。"""
    return StoragePressureInjector()


# ==================== 基类测试 ====================

class TestInjectContext:
    """测试注入上下文数据类。"""

    def test_context_creation(self, mock_executor):
        """测试创建注入上下文。"""
        context = InjectContext(
            scenario_run_id=1,
            device_serial="test_device",
            executor=mock_executor,
            fault_profile={"test": "data"},
            artifacts_dir="/tmp",
        )

        assert context.scenario_run_id == 1
        assert context.device_serial == "test_device"
        assert context.executor == mock_executor
        assert context.fault_profile == {"test": "data"}
        assert context.artifacts_dir == "/tmp"
        assert context.inject_stage == "precheck"

    def test_context_with_custom_stage(self, mock_executor):
        """测试自定义注入阶段的上下文。"""
        context = InjectContext(
            scenario_run_id=1,
            device_serial="test_device",
            executor=mock_executor,
            fault_profile={},
            artifacts_dir="/tmp",
            inject_stage="upgrading",
        )

        assert context.inject_stage == "upgrading"

    def test_context_timestamp(self, mock_executor):
        """测试上下文时间戳。"""
        before = datetime.utcnow()
        context = InjectContext(
            scenario_run_id=1,
            device_serial="test_device",
            executor=mock_executor,
            fault_profile={},
            artifacts_dir="/tmp",
        )
        after = datetime.utcnow()

        assert before <= context.started_at <= after


class TestInjectResult:
    """测试注入结果数据类。"""

    def test_result_creation_success(self):
        """测试创建成功的注入结果。"""
        result = InjectResult(
            success=True,
            fault_type="storage_pressure",
            fault_injected=True,
            fault_observed=True,
            message="注入成功",
            details={"pressure_mb": 500},
            cleanup_required=True,
        )

        assert result.success is True
        assert result.fault_injected is True
        assert result.fault_observed is True
        assert result.message == "注入成功"
        assert result.cleanup_required is True

    def test_result_creation_failure(self):
        """测试创建失败的注入结果。"""
        result = InjectResult(
            success=False,
            fault_type="storage_pressure",
            fault_injected=False,
            fault_observed=False,
            message="注入失败",
            cleanup_required=False,
        )

        assert result.success is False
        assert result.fault_injected is False
        assert result.fault_observed is False

    def test_result_default_values(self):
        """测试注入结果默认值。"""
        result = InjectResult(
            success=True,
            fault_type="test",
            fault_injected=True,
            fault_observed=False,
        )

        assert result.message == ""
        assert result.details == {}
        assert result.cleanup_required is True


class TestFaultTypeEnum:
    """测试注入器中的FaultType枚举。"""

    def test_all_fault_types(self):
        """测试所有故障类型枚举值。"""
        expected = [
            "storage_pressure",
            "low_battery",
            "network_jitter",
            "reboot_timeout",
            "cpu_io_stress",
            "monkey_stability",
        ]
        actual = [f.value for f in FaultType]
        assert actual == expected

    def test_fault_type_values_match_string(self):
        """测试枚举值与字符串匹配。"""
        assert FaultType.storage_pressure == "storage_pressure"
        assert FaultType.low_battery == "low_battery"


class TestRiskLevelEnum:
    """测试注入器中的RiskLevel枚举。"""

    def test_all_risk_levels(self):
        """测试所有风险等级枚举值。"""
        expected = ["low", "medium", "high", "critical"]
        actual = [r.value for r in RiskLevel]
        assert actual == expected


# ==================== 注册机制测试 ====================

class TestInjectorRegistry:
    """测试注入器注册机制。"""

    def test_registry_exists(self):
        """测试注册表存在。"""
        assert INJECTOR_REGISTRY is not None
        assert isinstance(INJECTOR_REGISTRY, dict)

    def test_register_injector(self):
        """测试注册注入器。"""
        # 创建测试注入器
        test_injector = MagicMock()
        test_injector.fault_type = "test_fault"

        # 注册
        register_injector(test_injector)

        # 验证注册成功
        assert "test_fault" in INJECTOR_REGISTRY
        assert INJECTOR_REGISTRY["test_fault"] == test_injector

    def test_get_injector_exists(self):
        """测试获取已注册的注入器。"""
        test_injector = MagicMock()
        test_injector.fault_type = "get_test"
        register_injector(test_injector)

        result = get_injector("get_test")
        assert result == test_injector

    def test_get_injector_not_exists(self):
        """测试获取未注册的注入器返回None。"""
        result = get_injector("nonexistent_fault")
        assert result is None

    def test_list_injectors(self):
        """测试列出所有注入器。"""
        # 列表应返回副本，不影响原注册表
        injectors = list_injectors()
        assert isinstance(injectors, dict)

        # 修改副本不应影响原注册表
        injectors["new_key"] = MagicMock()
        assert "new_key" not in INJECTOR_REGISTRY

    def test_storage_pressure_registered(self):
        """测试StoragePressureInjector已注册。"""
        # storage_pressure应已注册
        injector = get_injector("storage_pressure")
        assert injector is not None
        assert isinstance(injector, StoragePressureInjector)


# ==================== StoragePressureInjector 测试 ====================

class TestStoragePressureInjectorPrepare:
    """测试StoragePressureInjector的prepare方法。"""

    async def test_prepare_success(self, storage_injector, inject_context):
        """测试prepare成功。"""
        result = await storage_injector.prepare(inject_context)

        assert result is True
        assert storage_injector.pressure_mb == 500
        assert "target_path" in storage_injector.injected_files

    async def test_prepare_device_offline(self, storage_injector, inject_context_offline):
        """测试设备离线时prepare失败。"""
        result = await storage_injector.prepare(inject_context_offline)

        assert result is False

    async def test_prepare_insufficient_storage(self, storage_injector, inject_context_storage_full):
        """测试存储空间不足时prepare失败。"""
        result = await storage_injector.prepare(inject_context_storage_full)

        # 存储满设备只有50MB可用，无法注入500MB
        assert result is False

    async def test_prepare_custom_pressure_value(self, mock_executor):
        """测试自定义压力值。"""
        injector = StoragePressureInjector()
        context = InjectContext(
            scenario_run_id=1,
            device_serial="test",
            executor=mock_executor,
            fault_profile={"parameters": {"pressure_mb": 2000}},
            artifacts_dir="/tmp",
        )

        result = await injector.prepare(context)
        assert result is True
        assert injector.pressure_mb == 2000

    async def test_prepare_default_pressure_value(self, mock_executor):
        """测试默认压力值（1GB）。"""
        injector = StoragePressureInjector()
        context = InjectContext(
            scenario_run_id=1,
            device_serial="test",
            executor=mock_executor,
            fault_profile={"parameters": {}},  # 无压力参数
            artifacts_dir="/tmp",
        )

        result = await injector.prepare(context)
        assert result is True
        assert injector.pressure_mb == 1000  # 默认值

    async def test_prepare_custom_target_path(self, mock_executor):
        """测试自定义目标路径。"""
        injector = StoragePressureInjector()
        context = InjectContext(
            scenario_run_id=1,
            device_serial="test",
            executor=mock_executor,
            fault_profile={"parameters": {"target_path": "/custom/path"}},
            artifacts_dir="/tmp",
        )

        result = await injector.prepare(context)
        assert result is True
        assert injector.injected_files["target_path"] == "/custom/path"


class TestStoragePressureInjectorInject:
    """测试StoragePressureInjector的inject方法。"""

    async def test_inject_mock_mode_success(self, storage_injector, inject_context, mock_executor):
        """测试Mock模式下注入成功。"""
        # 先prepare
        await storage_injector.prepare(inject_context)

        # 执行注入
        result = await storage_injector.inject(inject_context)

        assert result.success is True
        assert result.fault_injected is True
        assert result.fault_observed is True
        assert "Mock注入" in result.message
        assert result.cleanup_required is True

    async def test_inject_mock_mode_state_change(self, storage_injector, inject_context, mock_executor):
        """测试Mock模式下注入改变设备状态。"""
        # 获取初始存储状态
        initial_storage = await mock_executor.get_storage_info()
        initial_available = initial_storage.available

        # prepare
        await storage_injector.prepare(inject_context)

        # inject
        await storage_injector.inject(inject_context)

        # 检查状态变化
        final_storage = await mock_executor.get_storage_info()
        final_available = final_storage.available

        # 存储应减少
        assert final_available < initial_available

    async def test_inject_returns_details(self, storage_injector, inject_context):
        """测试注入结果包含详细信息。"""
        await storage_injector.prepare(inject_context)
        result = await storage_injector.inject(inject_context)

        assert "pressure_mb" in result.details
        assert "available_before_mb" in result.details
        assert "available_after_mb" in result.details

    async def test_inject_fault_type_correct(self, storage_injector, inject_context):
        """测试注入结果fault_type正确。"""
        await storage_injector.prepare(inject_context)
        result = await storage_injector.inject(inject_context)

        assert result.fault_type == "storage_pressure"


class TestStoragePressureInjectorCleanup:
    """测试StoragePressureInjector的cleanup方法。"""

    async def test_cleanup_mock_mode_success(self, storage_injector, inject_context, mock_executor):
        """测试Mock模式下清理成功。"""
        # prepare
        await storage_injector.prepare(inject_context)

        # inject
        await storage_injector.inject(inject_context)

        # 清理前存储状态
        storage_before_cleanup = await mock_executor.get_storage_info()

        # cleanup
        result = await storage_injector.cleanup(inject_context)

        assert result is True

        # 清理后存储恢复
        storage_after_cleanup = await mock_executor.get_storage_info()
        assert storage_after_cleanup.available >= storage_before_cleanup.available

    async def test_cleanup_without_injection(self, storage_injector, inject_context):
        """测试未注入时清理仍成功。"""
        result = await storage_injector.cleanup(inject_context)
        assert result is True  # 无注入文件时清理返回True


class TestStoragePressureInjectorProperties:
    """测试StoragePressureInjector属性。"""

    def test_fault_type(self, storage_injector):
        """测试fault_type属性。"""
        assert storage_injector.fault_type == FaultType.storage_pressure

    def test_risk_level(self, storage_injector):
        """测试risk_level属性。"""
        assert storage_injector.risk_level == RiskLevel.medium

    def test_get_risk_level_method(self, storage_injector):
        """测试get_risk_level方法。"""
        assert storage_injector.get_risk_level() == RiskLevel.medium

    def test_get_description(self, storage_injector):
        """测试get_description方法。"""
        description = storage_injector.get_description()
        assert "存储" in description or "压力" in description

    def test_initial_state(self):
        """测试注入器初始状态。"""
        injector = StoragePressureInjector()
        assert injector.injected_files == {}
        assert injector.pressure_mb == 0


class TestStoragePressureInjectorMockScenario:
    """测试StoragePressureInjector在不同Mock场景下的表现。"""

    async def test_normal_scenario_flow(self):
        """测试正常场景的完整流程。"""
        executor = MockDeviceExecutor("normal_device", MockScenario.normal)
        injector = StoragePressureInjector()
        context = InjectContext(
            scenario_run_id=1,
            device_serial="normal_device",
            executor=executor,
            fault_profile={"parameters": {"pressure_mb": 100}},
            artifacts_dir="/tmp",
        )

        # 完整流程
        prepare_result = await injector.prepare(context)
        assert prepare_result is True

        inject_result = await injector.inject(context)
        assert inject_result.success is True

        cleanup_result = await injector.cleanup(context)
        assert cleanup_result is True

    async def test_offline_scenario_prepare_fails(self):
        """测试离线场景prepare失败。"""
        executor = MockDeviceExecutor("offline", MockScenario.offline)
        injector = StoragePressureInjector()
        context = InjectContext(
            scenario_run_id=1,
            device_serial="offline",
            executor=executor,
            fault_profile={"parameters": {"pressure_mb": 100}},
            artifacts_dir="/tmp",
        )

        result = await injector.prepare(context)
        assert result is False

    async def test_storage_full_scenario_prepare_fails(self):
        """测试存储满场景prepare失败。"""
        executor = MockDeviceExecutor("storage_full", MockScenario.storage_full)
        injector = StoragePressureInjector()
        context = InjectContext(
            scenario_run_id=1,
            device_serial="storage_full",
            executor=executor,
            fault_profile={"parameters": {"pressure_mb": 500}},
            artifacts_dir="/tmp",
        )

        result = await injector.prepare(context)
        assert result is False


# ==================== BaseInjector抽象类测试 ====================

class TestBaseInjectorAbstract:
    """测试BaseInjector抽象方法。"""

    def test_cannot_instantiate_directly(self):
        """测试不能直接实例化BaseInjector。"""
        with pytest.raises(TypeError):
            BaseInjector()

    def test_subclass_must_implement_all_methods(self):
        """测试子类必须实现所有抽象方法。"""
        class IncompleteInjector(BaseInjector):
            fault_type = FaultType.storage_pressure

            async def prepare(self, context):
                return True

            # 缺少inject和cleanup方法

        with pytest.raises(TypeError):
            IncompleteInjector()

    def test_complete_subclass_can_instantiate(self):
        """测试完整子类可以实例化。"""
        class CompleteInjector(BaseInjector):
            fault_type = FaultType.storage_pressure
            risk_level = RiskLevel.low

            async def prepare(self, context):
                return True

            async def inject(self, context):
                return InjectResult(success=True, fault_type="test", fault_injected=True, fault_observed=True)

            async def cleanup(self, context):
                return True

        injector = CompleteInjector()
        assert injector.fault_type == FaultType.storage_pressure
        assert injector.risk_level == RiskLevel.low


# ==================== Mock设备状态交互测试 ====================

class TestMockDeviceStateInteraction:
    """测试注入器与MockDeviceState的交互。"""

    async def test_apply_injection_storage_pressure(self, mock_executor):
        """测试应用存储压力注入到Mock设备状态。"""
        state = mock_executor.get_state()
        initial_available = state.storage_available

        state.apply_injection("storage_pressure", {"pressure_mb": 100})

        expected_reduction = 100 * 1024 * 1024
        assert state.storage_available == initial_available - expected_reduction

    async def test_apply_injection_low_battery(self, mock_executor):
        """测试应用低电量注入到Mock设备状态。"""
        state = mock_executor.get_state()

        state.apply_injection("low_battery", {"level": 10})

        assert state.battery_level == 10

    async def test_apply_injection_network_jitter(self, mock_executor):
        """测试应用网络波动注入到Mock设备状态。"""
        state = mock_executor.get_state()

        state.apply_injection("network_jitter", {})

        assert state.network_connected is False

    async def test_apply_injection_cpu_io_stress(self, mock_executor):
        """测试应用CPU/I/O压力注入到Mock设备状态。"""
        state = mock_executor.get_state()

        state.apply_injection("cpu_io_stress", {})

        assert len(state.stress_processes) > 0

    async def test_apply_recovery_cleanup_storage(self, mock_executor):
        """测试应用存储清理恢复到Mock设备状态。"""
        state = mock_executor.get_state()
        state.apply_injection("storage_pressure", {"pressure_mb": 100})

        state.apply_recovery("cleanup_storage", {"pressure_mb": 100})

        # 存储应恢复
        assert state.storage_available > 0

    async def test_apply_recovery_reset_battery(self, mock_executor):
        """测试应用电池重置恢复到Mock设备状态。"""
        state = mock_executor.get_state()
        state.apply_injection("low_battery", {"level": 5})

        state.apply_recovery("reset_battery", {})

        assert state.battery_level == 100

    async def test_apply_recovery_reset_network(self, mock_executor):
        """测试应用网络重置恢复到Mock设备状态。"""
        state = mock_executor.get_state()
        state.apply_injection("network_jitter", {})

        state.apply_recovery("reset_network", {})

        assert state.network_connected is True

    async def test_state_reset(self, mock_executor):
        """测试Mock设备状态重置。"""
        state = mock_executor.get_state()
        state.apply_injection("storage_pressure", {"pressure_mb": 500})
        state.apply_injection("low_battery", {"level": 10})

        state.reset()

        assert state.storage_available == 10 * 1024 * 1024 * 1024  # 10GB
        assert state.battery_level == 100
        assert state.network_connected is True