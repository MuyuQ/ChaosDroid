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
        # 注入器状态已移到inject()方法的本地变量，不再存储在实例属性中

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
        # 状态已移到inject()方法的本地变量

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
        # 默认值在inject()中使用，不再存储在实例属性

    async def test_prepare_custom_target_path(self, mock_executor):
        """测试自定义目标路径。"""
        injector = StoragePressureInjector()
        context = InjectContext(
            scenario_run_id=1,
            device_serial="test",
            executor=mock_executor,
            fault_profile={"parameters": {"target_path": "/sdcard/custom"}},
            artifacts_dir="/tmp",
        )

        result = await injector.prepare(context)
        assert result is True
        # 目标路径在inject()中使用，不再存储在实例属性


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
        """测试注入器初始状态（无实例属性）。"""
        injector = StoragePressureInjector()
        # 注入器不再维护实例状态，每次inject()独立运行
        assert hasattr(injector, 'fault_type')
        assert hasattr(injector, 'risk_level')


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


# ==================== LowBatteryInjector 测试 ====================

class TestLowBatteryInjector:
    """测试低电量注入器。"""

    @pytest.fixture
    def low_battery_injector(self):
        """创建低电量注入器实例。"""
        from chaosdroid.injectors.low_battery import LowBatteryInjector
        return LowBatteryInjector()

    @pytest.fixture
    def inject_context_low_battery(self, mock_executor):
        """创建低电量注入上下文。"""
        return InjectContext(
            scenario_run_id=1,
            device_serial="test_device",
            executor=mock_executor,
            fault_profile={"parameters": {"target_level": 10}},
            artifacts_dir="/tmp",
        )

    async def test_prepare_success(self, low_battery_injector, inject_context_low_battery):
        """测试低电量注入器准备成功。"""
        result = await low_battery_injector.prepare(inject_context_low_battery)
        assert result is True
        # 状态已移到inject()方法的本地变量

    async def test_prepare_offline_fails(self, low_battery_injector, mock_executor_offline):
        """测试离线设备准备失败。"""
        context = InjectContext(
            scenario_run_id=1,
            device_serial="offline",
            executor=mock_executor_offline,
            fault_profile={"parameters": {"target_level": 10}},
            artifacts_dir="/tmp",
        )
        result = await low_battery_injector.prepare(context)
        assert result is False

    async def test_inject_mock_mode(self, low_battery_injector, inject_context_low_battery, mock_executor):
        """测试Mock模式下低电量注入。"""
        await low_battery_injector.prepare(inject_context_low_battery)
        result = await low_battery_injector.inject(inject_context_low_battery)

        assert result.success is True
        assert result.fault_injected is True
        assert "Mock注入" in result.message

    async def test_inject_changes_state(self, low_battery_injector, inject_context_low_battery, mock_executor):
        """测试注入改变设备状态。"""
        state = mock_executor.get_state()
        await low_battery_injector.prepare(inject_context_low_battery)
        await low_battery_injector.inject(inject_context_low_battery)

        assert state.battery_level == 10

    async def test_cleanup_mock_mode(self, low_battery_injector, inject_context_low_battery, mock_executor):
        """测试Mock模式下清理。"""
        state = mock_executor.get_state()
        await low_battery_injector.prepare(inject_context_low_battery)
        await low_battery_injector.inject(inject_context_low_battery)

        result = await low_battery_injector.cleanup(inject_context_low_battery)

        assert result is True
        assert state.battery_level == 100

    def test_fault_type(self, low_battery_injector):
        """测试故障类型属性。"""
        from chaosdroid.injectors.base import FaultType
        assert low_battery_injector.fault_type == FaultType.low_battery

    def test_risk_level(self, low_battery_injector):
        """测试风险等级属性。"""
        from chaosdroid.injectors.base import RiskLevel
        assert low_battery_injector.risk_level == RiskLevel.low


# ==================== NetworkJitterInjector 测试 ====================

class TestNetworkJitterInjector:
    """测试网络波动注入器。"""

    @pytest.fixture
    def network_injector(self):
        """创建网络波动注入器实例。"""
        from chaosdroid.injectors.network_jitter import NetworkJitterInjector
        return NetworkJitterInjector()

    @pytest.fixture
    def inject_context_network(self, mock_executor):
        """创建网络波动注入上下文。"""
        return InjectContext(
            scenario_run_id=1,
            device_serial="test_device",
            executor=mock_executor,
            fault_profile={"parameters": {
                "jitter_type": "disconnect",
                "latency_ms": 500,
                "disconnect_duration_sec": 5
            }},
            artifacts_dir="/tmp",
        )

    async def test_prepare_success(self, network_injector, inject_context_network):
        """测试网络波动注入器准备成功。"""
        result = await network_injector.prepare(inject_context_network)
        assert result is True
        # 状态已移到inject()方法的本地变量

    async def test_prepare_offline_fails(self, network_injector, mock_executor_offline):
        """测试离线设备准备失败。"""
        context = InjectContext(
            scenario_run_id=1,
            device_serial="offline",
            executor=mock_executor_offline,
            fault_profile={"parameters": {"jitter_type": "latency"}},
            artifacts_dir="/tmp",
        )
        result = await network_injector.prepare(context)
        assert result is False

    async def test_inject_mock_mode_disconnect(self, network_injector, inject_context_network, mock_executor):
        """测试Mock模式下断网注入。"""
        state = mock_executor.get_state()
        await network_injector.prepare(inject_context_network)
        result = await network_injector.inject(inject_context_network)

        assert result.success is True
        assert result.fault_injected is True
        assert state.network_connected is False

    async def test_inject_mock_mode_timeout(self, network_injector, mock_executor):
        """测试Mock模式下超时注入。"""
        context = InjectContext(
            scenario_run_id=1,
            device_serial="test",
            executor=mock_executor,
            fault_profile={"parameters": {"jitter_type": "timeout"}},
            artifacts_dir="/tmp",
        )
        state = mock_executor.get_state()
        await network_injector.prepare(context)
        result = await network_injector.inject(context)

        assert result.success is True

    async def test_cleanup_mock_mode(self, network_injector, inject_context_network, mock_executor):
        """测试Mock模式下清理。"""
        state = mock_executor.get_state()
        await network_injector.prepare(inject_context_network)
        await network_injector.inject(inject_context_network)

        result = await network_injector.cleanup(inject_context_network)

        assert result is True
        assert state.network_connected is True

    def test_fault_type(self, network_injector):
        """测试故障类型属性。"""
        from chaosdroid.injectors.base import FaultType
        assert network_injector.fault_type == FaultType.network_jitter

    def test_risk_level(self, network_injector):
        """测试风险等级属性。"""
        from chaosdroid.injectors.base import RiskLevel
        assert network_injector.risk_level == RiskLevel.medium


# ==================== RebootTimeoutInjector 测试 ====================

class TestRebootTimeoutInjector:
    """测试重启超时注入器。"""

    @pytest.fixture
    def reboot_injector(self):
        """创建重启超时注入器实例。"""
        from chaosdroid.injectors.reboot_timeout import RebootTimeoutInjector
        return RebootTimeoutInjector()

    @pytest.fixture
    def inject_context_reboot(self, mock_executor):
        """创建重启超时注入上下文。"""
        return InjectContext(
            scenario_run_id=1,
            device_serial="test_device",
            executor=mock_executor,
            fault_profile={"parameters": {
                "timeout_duration_sec": 60,
                "boot_delay_sec": 30
            }},
            artifacts_dir="/tmp",
        )

    async def test_prepare_success(self, reboot_injector, inject_context_reboot):
        """测试重启超时注入器准备成功。"""
        result = await reboot_injector.prepare(inject_context_reboot)
        assert result is True
        # 状态已移到inject()方法的本地变量

    async def test_prepare_offline_fails(self, reboot_injector, mock_executor_offline):
        """测试离线设备准备失败。"""
        context = InjectContext(
            scenario_run_id=1,
            device_serial="offline",
            executor=mock_executor_offline,
            fault_profile={"parameters": {"timeout_duration_sec": 60}},
            artifacts_dir="/tmp",
        )
        result = await reboot_injector.prepare(context)
        assert result is False

    async def test_inject_mock_mode(self, reboot_injector, inject_context_reboot, mock_executor):
        """测试Mock模式下重启超时注入。"""
        state = mock_executor.get_state()
        await reboot_injector.prepare(inject_context_reboot)
        result = await reboot_injector.inject(inject_context_reboot)

        assert result.success is True
        assert result.fault_injected is True
        assert state.boot_completed is False

    async def test_inject_sets_boot_not_completed(self, reboot_injector, inject_context_reboot, mock_executor):
        """测试注入设置boot未完成状态。"""
        state = mock_executor.get_state()
        state.boot_completed = True  # 初始为True

        await reboot_injector.prepare(inject_context_reboot)
        await reboot_injector.inject(inject_context_reboot)

        assert state.boot_completed is False

    async def test_cleanup_mock_mode(self, reboot_injector, inject_context_reboot, mock_executor):
        """测试Mock模式下清理。"""
        state = mock_executor.get_state()
        await reboot_injector.prepare(inject_context_reboot)
        await reboot_injector.inject(inject_context_reboot)

        result = await reboot_injector.cleanup(inject_context_reboot)

        assert result is True
        assert state.boot_completed is True

    def test_fault_type(self, reboot_injector):
        """测试故障类型属性。"""
        from chaosdroid.injectors.base import FaultType
        assert reboot_injector.fault_type == FaultType.reboot_timeout

    def test_risk_level(self, reboot_injector):
        """测试风险等级属性。"""
        from chaosdroid.injectors.base import RiskLevel
        assert reboot_injector.risk_level == RiskLevel.high


# ==================== CpuIoStressInjector 测试 ====================

class TestCpuIoStressInjector:
    """测试CPU/I/O压力注入器。"""

    @pytest.fixture
    def cpu_io_injector(self):
        """创建CPU/I/O压力注入器实例。"""
        from chaosdroid.injectors.cpu_io_stress import CpuIoStressInjector
        return CpuIoStressInjector()

    @pytest.fixture
    def inject_context_cpu_io(self, mock_executor):
        """创建CPU/I/O压力注入上下文。"""
        return InjectContext(
            scenario_run_id=1,
            device_serial="test_device",
            executor=mock_executor,
            fault_profile={"parameters": {
                "cpu_load_percent": 50,
                "io_enabled": True,
                "duration_sec": 60
            }},
            artifacts_dir="/tmp",
        )

    async def test_prepare_success(self, cpu_io_injector, inject_context_cpu_io):
        """测试CPU/I/O压力注入器准备成功。"""
        result = await cpu_io_injector.prepare(inject_context_cpu_io)
        assert result is True
        # 状态已移到inject()方法的本地变量

    async def test_prepare_offline_fails(self, cpu_io_injector, mock_executor_offline):
        """测试离线设备准备失败。"""
        context = InjectContext(
            scenario_run_id=1,
            device_serial="offline",
            executor=mock_executor_offline,
            fault_profile={"parameters": {"cpu_load_percent": 50}},
            artifacts_dir="/tmp",
        )
        result = await cpu_io_injector.prepare(context)
        assert result is False

    async def test_inject_mock_mode(self, cpu_io_injector, inject_context_cpu_io, mock_executor):
        """测试Mock模式下CPU/I/O压力注入。"""
        state = mock_executor.get_state()
        await cpu_io_injector.prepare(inject_context_cpu_io)
        result = await cpu_io_injector.inject(inject_context_cpu_io)

        assert result.success is True
        assert result.fault_injected is True
        assert len(state.stress_processes) > 0

    async def test_inject_adds_stress_process(self, cpu_io_injector, inject_context_cpu_io, mock_executor):
        """测试注入添加压力进程。"""
        state = mock_executor.get_state()
        initial_count = len(state.stress_processes)

        await cpu_io_injector.prepare(inject_context_cpu_io)
        await cpu_io_injector.inject(inject_context_cpu_io)

        assert len(state.stress_processes) > initial_count

    async def test_cleanup_mock_mode(self, cpu_io_injector, inject_context_cpu_io, mock_executor):
        """测试Mock模式下清理。"""
        state = mock_executor.get_state()
        await cpu_io_injector.prepare(inject_context_cpu_io)
        await cpu_io_injector.inject(inject_context_cpu_io)

        result = await cpu_io_injector.cleanup(inject_context_cpu_io)

        assert result is True
        assert len(state.stress_processes) == 0

    def test_fault_type(self, cpu_io_injector):
        """测试故障类型属性。"""
        from chaosdroid.injectors.base import FaultType
        assert cpu_io_injector.fault_type == FaultType.cpu_io_stress

    def test_risk_level(self, cpu_io_injector):
        """测试风险等级属性。"""
        from chaosdroid.injectors.base import RiskLevel
        assert cpu_io_injector.risk_level == RiskLevel.medium


# ==================== MonkeyStabilityInjector 测试 ====================

class TestMonkeyStabilityInjector:
    """测试Monkey稳定性注入器。"""

    @pytest.fixture
    def monkey_injector(self):
        """创建Monkey稳定性注入器实例。"""
        from chaosdroid.injectors.monkey_stability import MonkeyStabilityInjector
        return MonkeyStabilityInjector()

    @pytest.fixture
    def inject_context_monkey(self, mock_executor):
        """创建Monkey稳定性注入上下文。"""
        return InjectContext(
            scenario_run_id=1,
            device_serial="test_device",
            executor=mock_executor,
            fault_profile={"parameters": {
                "package": "com.test.app",
                "event_count": 1000,
                "seed": 123,
                "throttle_ms": 50,
                "options": {
                    "max_crashes_allowed": 0,
                    "max_anrs_allowed": 0
                }
            }},
            artifacts_dir="/tmp",
        )

    async def test_prepare_success(self, monkey_injector, inject_context_monkey):
        """测试Monkey稳定性注入器准备成功。"""
        result = await monkey_injector.prepare(inject_context_monkey)
        assert result is True
        # 状态已移到inject()方法的本地变量

    async def test_prepare_offline_fails(self, monkey_injector, mock_executor_offline):
        """测试离线设备准备失败。"""
        context = InjectContext(
            scenario_run_id=1,
            device_serial="offline",
            executor=mock_executor_offline,
            fault_profile={"parameters": {"event_count": 1000}},
            artifacts_dir="/tmp",
        )
        result = await monkey_injector.prepare(context)
        assert result is False

    async def test_inject_mock_mode(self, monkey_injector, inject_context_monkey):
        """测试Mock模式下Monkey稳定性注入。"""
        await monkey_injector.prepare(inject_context_monkey)
        result = await monkey_injector.inject(inject_context_monkey)

        assert result.success is True
        assert result.fault_injected is True
        assert "crash_count" in result.details
        assert "anr_count" in result.details

    async def test_inject_returns_monkey_stats(self, monkey_injector, inject_context_monkey):
        """测试注入返回Monkey统计信息。"""
        await monkey_injector.prepare(inject_context_monkey)
        result = await monkey_injector.inject(inject_context_monkey)

        assert "total_events" in result.details
        assert result.details["total_events"] == 1000

    async def test_cleanup_success(self, monkey_injector, inject_context_monkey):
        """测试Monkey清理成功（Monkey测试不需要清理）。"""
        await monkey_injector.prepare(inject_context_monkey)
        result = await monkey_injector.cleanup(inject_context_monkey)

        assert result is True

    def test_fault_type(self, monkey_injector):
        """测试故障类型属性。"""
        from chaosdroid.injectors.base import FaultType
        assert monkey_injector.fault_type == FaultType.monkey_stability

    def test_risk_level(self, monkey_injector):
        """测试风险等级属性。"""
        from chaosdroid.injectors.base import RiskLevel
        assert monkey_injector.risk_level == RiskLevel.medium

    def test_parse_crashes(self, monkey_injector):
        """测试解析crash输出。"""
        output = """
// CRASH: com.test.app (pid 1234)
Events injected: 500
// CRASH: com.test.app (pid 5678)
"""
        count = monkey_injector._parse_crashes(output)
        assert count == 2

    def test_parse_anrs(self, monkey_injector):
        """测试解析ANR输出。"""
        output = """
// ANR: com.test.app
Events injected: 500
// ANR: com.test.app
"""
        count = monkey_injector._parse_anrs(output)
        assert count == 2


# ==================== 注入器注册测试 ====================

class TestInjectorRegistration:
    """测试所有注入器已正确注册。"""

    def test_all_injectors_registered(self):
        """测试所有6类注入器已注册。"""
        expected_types = [
            "storage_pressure",
            "low_battery",
            "network_jitter",
            "reboot_timeout",
            "cpu_io_stress",
            "monkey_stability",
        ]

        for fault_type in expected_types:
            injector = get_injector(fault_type)
            assert injector is not None, f"{fault_type} injector not registered"

    def test_get_injector_by_fault_type(self):
        """测试按故障类型获取注入器。"""
        from chaosdroid.injectors.storage_pressure import StoragePressureInjector
        from chaosdroid.injectors.low_battery import LowBatteryInjector
        from chaosdroid.injectors.network_jitter import NetworkJitterInjector
        from chaosdroid.injectors.reboot_timeout import RebootTimeoutInjector
        from chaosdroid.injectors.cpu_io_stress import CpuIoStressInjector
        from chaosdroid.injectors.monkey_stability import MonkeyStabilityInjector

        assert isinstance(get_injector("storage_pressure"), StoragePressureInjector)
        assert isinstance(get_injector("low_battery"), LowBatteryInjector)
        assert isinstance(get_injector("network_jitter"), NetworkJitterInjector)
        assert isinstance(get_injector("reboot_timeout"), RebootTimeoutInjector)
        assert isinstance(get_injector("cpu_io_stress"), CpuIoStressInjector)
        assert isinstance(get_injector("monkey_stability"), MonkeyStabilityInjector)


# ==================== Mock模式 vs Real模式测试 ====================

class TestMockVsRealMode:
    """测试Mock模式和Real模式的处理差异。"""

    async def test_storage_pressure_mock_mode(self, mock_executor):
        """测试存储压力注入在Mock模式下正确处理。"""
        injector = StoragePressureInjector()
        context = InjectContext(
            scenario_run_id=1,
            device_serial="test",
            executor=mock_executor,
            fault_profile={"parameters": {"pressure_mb": 100}},
            artifacts_dir="/tmp",
        )

        await injector.prepare(context)
        result = await injector.inject(context)

        assert "Mock注入" in result.message

    async def test_low_battery_mock_mode(self, mock_executor):
        """测试低电量注入在Mock模式下正确处理。"""
        from chaosdroid.injectors.low_battery import LowBatteryInjector
        injector = LowBatteryInjector()
        context = InjectContext(
            scenario_run_id=1,
            device_serial="test",
            executor=mock_executor,
            fault_profile={"parameters": {"target_level": 10}},
            artifacts_dir="/tmp",
        )

        await injector.prepare(context)
        result = await injector.inject(context)

        # Mock模式应修改状态
        state = mock_executor.get_state()
        assert state.battery_level == 10

    async def test_network_jitter_mock_mode(self, mock_executor):
        """测试网络波动注入在Mock模式下正确处理。"""
        from chaosdroid.injectors.network_jitter import NetworkJitterInjector
        injector = NetworkJitterInjector()
        context = InjectContext(
            scenario_run_id=1,
            device_serial="test",
            executor=mock_executor,
            fault_profile={"parameters": {"jitter_type": "disconnect"}},
            artifacts_dir="/tmp",
        )

        await injector.prepare(context)
        result = await injector.inject(context)

        # Mock模式应修改网络状态
        state = mock_executor.get_state()
        assert state.network_connected is False

    async def test_reboot_timeout_mock_mode(self, mock_executor):
        """测试重启超时注入在Mock模式下正确处理。"""
        from chaosdroid.injectors.reboot_timeout import RebootTimeoutInjector
        injector = RebootTimeoutInjector()
        context = InjectContext(
            scenario_run_id=1,
            device_serial="test",
            executor=mock_executor,
            fault_profile={"parameters": {}},
            artifacts_dir="/tmp",
        )

        await injector.prepare(context)
        result = await injector.inject(context)

        # Mock模式应设置boot未完成
        state = mock_executor.get_state()
        assert state.boot_completed is False

    async def test_cpu_io_stress_mock_mode(self, mock_executor):
        """测试CPU/I/O压力注入在Mock模式下正确处理。"""
        from chaosdroid.injectors.cpu_io_stress import CpuIoStressInjector
        injector = CpuIoStressInjector()
        context = InjectContext(
            scenario_run_id=1,
            device_serial="test",
            executor=mock_executor,
            fault_profile={"parameters": {}},
            artifacts_dir="/tmp",
        )

        await injector.prepare(context)
        result = await injector.inject(context)

        # Mock模式应添加压力进程
        state = mock_executor.get_state()
        assert len(state.stress_processes) > 0

    def test_executor_has_get_state_method(self, mock_executor):
        """测试Mock执行器有get_state方法用于判断Mock模式。"""
        # 注入器使用 hasattr(executor, 'get_state') 来判断是否是Mock模式
        assert hasattr(mock_executor, 'get_state')
        assert callable(getattr(mock_executor, 'get_state'))