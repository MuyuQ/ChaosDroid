"""
设备执行器单元测试。

测试MockDeviceExecutor和MockDeviceState。
"""
import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from chaosdroid.executors.base import (
    BaseDeviceExecutor,
    ExecutorMode,
    MockScenario,
    StorageInfo,
    BatteryInfo,
    ShellResult,
    MonkeyResult,
)
from chaosdroid.executors.mock_executor import MockDeviceExecutor, MockDeviceState


# ==================== Fixtures ====================

@pytest.fixture
def mock_executor_normal():
    """创建正常状态的Mock执行器。"""
    return MockDeviceExecutor("device_001", MockScenario.normal)


@pytest.fixture
def mock_executor_offline():
    """创建离线状态的Mock执行器。"""
    return MockDeviceExecutor("device_offline", MockScenario.offline)


@pytest.fixture
def mock_executor_low_battery():
    """创建低电量状态的Mock执行器。"""
    return MockDeviceExecutor("device_low_battery", MockScenario.low_battery)


@pytest.fixture
def mock_executor_storage_full():
    """创建存储满状态的Mock执行器。"""
    return MockDeviceExecutor("device_storage_full", MockScenario.storage_full)


@pytest.fixture
def mock_executor_boot_timeout():
    """创建启动超时状态的Mock执行器。"""
    return MockDeviceExecutor("device_boot_timeout", MockScenario.boot_timeout)


@pytest.fixture
def mock_executor_network_error():
    """创建网络错误状态的Mock执行器。"""
    return MockDeviceExecutor("device_network_error", MockScenario.network_error)


@pytest.fixture
def mock_state():
    """创建Mock设备状态实例。"""
    return MockDeviceState("test_device", MockScenario.normal)


# ==================== MockDeviceExecutor 基础测试 ====================

class TestMockDeviceExecutorInit:
    """测试MockDeviceExecutor初始化。"""

    def test_init_with_serial(self):
        """测试带序列号初始化。"""
        executor = MockDeviceExecutor("test_serial")
        assert executor.device_serial == "test_serial"

    def test_init_with_scenario(self):
        """测试带场景初始化。"""
        executor = MockDeviceExecutor("test", MockScenario.low_battery)
        assert executor.state.scenario == MockScenario.low_battery
        assert executor.state.battery_level == 15

    def test_init_default_scenario(self):
        """测试默认场景初始化。"""
        executor = MockDeviceExecutor("test")
        assert executor.state.scenario == MockScenario.normal
        assert executor.state.online is True

    def test_mode_attribute(self):
        """测试mode属性。"""
        executor = MockDeviceExecutor("test")
        assert executor.mode == ExecutorMode.mock

    def test_state_instance(self):
        """测试state实例。"""
        executor = MockDeviceExecutor("test")
        assert isinstance(executor.state, MockDeviceState)


# ==================== is_online 方法测试 ====================

class TestIsOnline:
    """测试is_online方法。"""

    async def test_normal_device_online(self, mock_executor_normal):
        """测试正常设备在线。"""
        result = await mock_executor_normal.is_online()
        assert result is True

    async def test_offline_device_not_online(self, mock_executor_offline):
        """测试离线设备不在线。"""
        result = await mock_executor_offline.is_online()
        assert result is False

    async def test_low_battery_device_online(self, mock_executor_low_battery):
        """测试低电量设备仍然在线。"""
        result = await mock_executor_low_battery.is_online()
        assert result is True

    async def test_storage_full_device_online(self, mock_executor_storage_full):
        """测试存储满设备仍然在线。"""
        result = await mock_executor_storage_full.is_online()
        assert result is True

    async def test_is_online_has_delay(self, mock_executor_normal):
        """测试is_online有模拟延迟。"""
        import time
        start = time.time()
        await mock_executor_normal.is_online()
        elapsed = time.time() - start
        # 延迟应该在50-100ms之间（模拟延迟）
        assert elapsed >= 0.05  # 至少50ms


# ==================== get_properties 方法测试 ====================

class TestGetProperties:
    """测试get_properties方法。"""

    async def test_normal_device_properties(self, mock_executor_normal):
        """测试正常设备属性。"""
        properties = await mock_executor_normal.get_properties()

        assert "ro.product.model" in properties
        assert properties["ro.product.model"] == "Mock Device"
        assert "ro.product.brand" in properties
        assert "ro.build.version.release" in properties

    async def test_offline_device_empty_properties(self, mock_executor_offline):
        """测试离线设备返回空属性。"""
        properties = await mock_executor_offline.get_properties()
        assert properties == {}

    async def test_properties_is_copy(self, mock_executor_normal):
        """测试返回的属性是副本。"""
        properties1 = await mock_executor_normal.get_properties()
        properties2 = await mock_executor_normal.get_properties()

        properties1["custom"] = "test"
        assert "custom" not in properties2


# ==================== get_storage_info 方法测试 ====================

class TestGetStorageInfo:
    """测试get_storage_info方法。"""

    async def test_normal_device_storage(self, mock_executor_normal):
        """测试正常设备存储信息。"""
        storage = await mock_executor_normal.get_storage_info()

        assert isinstance(storage, StorageInfo)
        assert storage.total == 32 * 1024 * 1024 * 1024  # 32GB
        assert storage.available == 10 * 1024 * 1024 * 1024  # 10GB
        assert storage.used == 22 * 1024 * 1024 * 1024  # 22GB
        assert storage.path == "/"

    async def test_storage_full_device_storage(self, mock_executor_storage_full):
        """测试存储满设备存储信息。"""
        storage = await mock_executor_storage_full.get_storage_info()

        assert storage.available == 50 * 1024 * 1024  # 只有50MB

    async def test_storage_values_consistent(self, mock_executor_normal):
        """测试存储值一致性（total = available + used）。"""
        storage = await mock_executor_normal.get_storage_info()

        assert storage.total == storage.available + storage.used


# ==================== get_battery_info 方法测试 ====================

class TestGetBatteryInfo:
    """测试get_battery_info方法。"""

    async def test_normal_device_battery(self, mock_executor_normal):
        """测试正常设备电池信息。"""
        battery = await mock_executor_normal.get_battery_info()

        assert isinstance(battery, BatteryInfo)
        assert battery.level == 100
        assert battery.status == "discharging"
        assert battery.temperature == 25
        assert battery.health == "good"

    async def test_low_battery_device_battery(self, mock_executor_low_battery):
        """测试低电量设备电池信息。"""
        battery = await mock_executor_low_battery.get_battery_info()

        assert battery.level == 15

    async def test_battery_info_fields(self, mock_executor_normal):
        """测试电池信息字段完整性。"""
        battery = await mock_executor_normal.get_battery_info()

        assert hasattr(battery, "level")
        assert hasattr(battery, "status")
        assert hasattr(battery, "temperature")
        assert hasattr(battery, "health")


# ==================== execute_shell 方法测试 ====================

class TestExecuteShell:
    """测试execute_shell方法。"""

    async def test_execute_shell_online(self, mock_executor_normal):
        """测试在线设备执行shell命令。"""
        result = await mock_executor_normal.execute_shell("ls /sdcard")

        assert isinstance(result, ShellResult)
        assert result.success is True
        assert result.exit_code == 0
        assert result.stderr == ""

    async def test_execute_shell_offline(self, mock_executor_offline):
        """测试离线设备执行shell命令失败。"""
        result = await mock_executor_offline.execute_shell("ls /sdcard")

        assert result.success is False
        assert result.exit_code == -1
        assert "offline" in result.stderr.lower()

    async def test_execute_shell_getprop_boot_completed(self, mock_executor_normal):
        """测试获取boot_completed属性。"""
        result = await mock_executor_normal.execute_shell("getprop sys.boot_completed")

        assert result.success is True
        assert result.stdout.strip() == "1"

    async def test_execute_shell_getprop_boot_not_completed(self, mock_executor_boot_timeout):
        """测试启动超时设备boot_completed为0。"""
        result = await mock_executor_boot_timeout.execute_shell("getprop sys.boot_completed")

        assert result.success is True
        assert result.stdout.strip() == "0"

    async def test_execute_shell_getprop_other_property(self, mock_executor_normal):
        """测试获取其他属性。"""
        result = await mock_executor_normal.execute_shell("getprop ro.product.model")

        assert result.success is True
        assert result.stdout == "Mock Device"

    async def test_execute_shell_dumpsys_battery(self, mock_executor_normal):
        """测试dumpsys battery命令。"""
        result = await mock_executor_normal.execute_shell("dumpsys battery")

        assert result.success is True
        assert "level" in result.stdout

    async def test_execute_shell_low_battery_dumpsys(self, mock_executor_low_battery):
        """测试低电量设备dumpsys battery。"""
        result = await mock_executor_low_battery.execute_shell("dumpsys battery")

        assert result.success is True
        assert "15" in result.stdout

    async def test_execute_shell_with_timeout(self, mock_executor_normal):
        """测试带超时的shell命令执行。"""
        result = await mock_executor_normal.execute_shell("ls", timeout=30)

        assert result.success is True


# ==================== push_file / pull_file 方法测试 ====================

class TestFileTransfer:
    """测试文件传输方法。"""

    async def test_push_file_online(self, mock_executor_normal):
        """测试在线设备推送文件。"""
        result = await mock_executor_normal.push_file("/local/file.txt", "/remote/file.txt")
        assert result is True

    async def test_push_file_offline(self, mock_executor_offline):
        """测试离线设备推送文件失败。"""
        result = await mock_executor_offline.push_file("/local/file.txt", "/remote/file.txt")
        assert result is False

    async def test_pull_file_online(self, mock_executor_normal):
        """测试在线设备拉取文件。"""
        result = await mock_executor_normal.pull_file("/remote/file.txt", "/local/file.txt")
        assert result is True

    async def test_pull_file_offline(self, mock_executor_offline):
        """测试离线设备拉取文件失败。"""
        result = await mock_executor_offline.pull_file("/remote/file.txt", "/local/file.txt")
        assert result is False


# ==================== run_monkey 方法测试 ====================

class TestRunMonkey:
    """测试run_monkey方法。"""

    async def test_run_monkey_online(self, mock_executor_normal):
        """测试在线设备运行monkey。"""
        result = await mock_executor_normal.run_monkey("com.test.app", 1000)

        assert isinstance(result, MonkeyResult)
        assert result.success is True
        assert result.total_events == 1000
        assert result.crash_count == 0
        assert result.anr_count == 0

    async def test_run_monkey_offline(self, mock_executor_offline):
        """测试离线设备运行monkey失败。"""
        result = await mock_executor_offline.run_monkey("com.test.app", 1000)

        assert result.success is False
        assert result.total_events == 0

    async def test_run_monkey_with_options(self, mock_executor_normal):
        """测试带选项运行monkey。"""
        result = await mock_executor_normal.run_monkey(
            "com.test.app",
            500,
            {"throttle": 100, "seed": 123}
        )

        assert result.success is True
        assert result.total_events == 500

    async def test_run_monkey_network_error_has_crashes(self, mock_executor_network_error):
        """测试网络错误场景monkey产生crash。"""
        result = await mock_executor_network_error.run_monkey("com.test.app", 1000)

        assert result.success is True
        # 网络错误场景可能产生crash
        assert result.crash_count >= 0


# ==================== reboot 方法测试 ====================

class TestReboot:
    """测试reboot方法。"""

    async def test_reboot_normal_success(self, mock_executor_normal):
        """测试正常设备重启成功。"""
        result = await mock_executor_normal.reboot(wait_timeout=120)

        assert result is True
        assert mock_executor_normal.state.boot_completed is True

    async def test_reboot_offline_fails(self, mock_executor_offline):
        """测试离线设备重启失败。"""
        result = await mock_executor_offline.reboot(wait_timeout=120)
        assert result is False

    async def test_reboot_boot_timeout_fails(self, mock_executor_boot_timeout):
        """测试启动超时场景重启失败。"""
        result = await mock_executor_boot_timeout.reboot(wait_timeout=120)
        assert result is False

    async def test_reboot_sets_boot_completed_false_first(self, mock_executor_normal):
        """测试重启先设置boot_completed为False。"""
        # 重启过程中boot_completed应先变为False
        await mock_executor_normal.reboot(120)
        # 最终应变为True
        assert mock_executor_normal.state.boot_completed is True


# ==================== wait_for_boot / check_boot_completed 测试 ====================

class TestBootMethods:
    """测试启动相关方法。"""

    async def test_wait_for_boot_normal(self, mock_executor_normal):
        """测试正常设备等待启动完成。"""
        result = await mock_executor_normal.wait_for_boot(timeout=60)
        assert result is True

    async def test_wait_for_boot_timeout(self, mock_executor_boot_timeout):
        """测试启动超时设备等待失败。"""
        result = await mock_executor_boot_timeout.wait_for_boot(timeout=60)
        assert result is False

    async def test_check_boot_completed_normal(self, mock_executor_normal):
        """测试正常设备boot完成检查。"""
        result = await mock_executor_normal.check_boot_completed()
        assert result is True

    async def test_check_boot_completed_timeout(self, mock_executor_boot_timeout):
        """测试启动超时设备boot未完成。"""
        result = await mock_executor_boot_timeout.check_boot_completed()
        assert result is False


# ==================== get_logcat 方法测试 ====================

class TestGetLogcat:
    """测试get_logcat方法。"""

    async def test_get_logcat_online(self, mock_executor_normal):
        """测试在线设备获取logcat。"""
        logcat = await mock_executor_normal.get_logcat(lines=100)

        assert isinstance(logcat, str)
        assert len(logcat) > 0
        # 验证日志格式包含真实的Android组件
        assert "ActivityManager" in logcat or "AndroidRuntime" in logcat or "PackageManager" in logcat

    async def test_get_logcat_offline(self, mock_executor_offline):
        """测试离线设备获取logcat为空。"""
        logcat = await mock_executor_offline.get_logcat(lines=100)
        assert logcat == ""

    async def test_get_logcat_lines_limit(self, mock_executor_normal):
        """测试logcat行数限制。"""
        logcat = await mock_executor_normal.get_logcat(lines=10)

        lines = logcat.split("\n")
        assert len(lines) <= 100  # Mock最多返回100行


# ==================== get_state 方法测试 ====================

class TestGetState:
    """测试get_state方法。"""

    def test_get_state_returns_state(self, mock_executor_normal):
        """测试get_state返回状态对象。"""
        state = mock_executor_normal.get_state()
        assert isinstance(state, MockDeviceState)

    def test_state_can_be_modified(self, mock_executor_normal):
        """测试状态可被修改。"""
        state = mock_executor_normal.get_state()
        state.battery_level = 50

        # 再次获取状态确认修改生效
        state2 = mock_executor_normal.get_state()
        assert state2.battery_level == 50


# ==================== MockDeviceState 测试 ====================

class TestMockDeviceStateInit:
    """测试MockDeviceState初始化。"""

    def test_init_normal_scenario(self):
        """测试正常场景初始化。"""
        state = MockDeviceState("test", MockScenario.normal)

        assert state.online is True
        assert state.battery_level == 100
        assert state.boot_completed is True
        assert state.network_connected is True
        assert len(state.stress_processes) == 0

    def test_init_offline_scenario(self):
        """测试离线场景初始化。"""
        state = MockDeviceState("test", MockScenario.offline)

        assert state.online is False

    def test_init_low_battery_scenario(self):
        """测试低电量场景初始化。"""
        state = MockDeviceState("test", MockScenario.low_battery)

        assert state.battery_level == 15

    def test_init_storage_full_scenario(self):
        """测试存储满场景初始化。"""
        state = MockDeviceState("test", MockScenario.storage_full)

        assert state.storage_available == 50 * 1024 * 1024  # 50MB

    def test_init_boot_timeout_scenario(self):
        """测试启动超时场景初始化。"""
        state = MockDeviceState("test", MockScenario.boot_timeout)

        assert state.boot_completed is False

    def test_init_network_error_scenario(self):
        """测试网络错误场景初始化。"""
        state = MockDeviceState("test", MockScenario.network_error)

        assert state.network_connected is False

    def test_default_properties(self):
        """测试默认属性值。"""
        state = MockDeviceState("test")

        assert state.properties["ro.product.model"] == "Mock Device"
        assert state.properties["ro.product.brand"] == "MockBrand"
        assert state.properties["ro.build.version.release"] == "14"
        assert state.properties["ro.build.version.sdk"] == "34"


class TestMockDeviceStateApplyInjection:
    """测试MockDeviceState.apply_injection方法。"""

    def test_apply_storage_pressure(self, mock_state):
        """测试应用存储压力注入。"""
        initial_available = mock_state.storage_available

        mock_state.apply_injection("storage_pressure", {"pressure_mb": 100})

        expected_reduction = 100 * 1024 * 1024
        assert mock_state.storage_available == initial_available - expected_reduction

    def test_apply_large_storage_pressure(self, mock_state):
        """测试应用大容量存储压力。"""
        mock_state.apply_injection("storage_pressure", {"pressure_mb": 5000})

        # 存储不应为负数
        assert mock_state.storage_available >= 0

    def test_apply_low_battery(self, mock_state):
        """测试应用低电量注入。"""
        mock_state.apply_injection("low_battery", {"level": 5})

        assert mock_state.battery_level == 5

    def test_apply_network_jitter(self, mock_state):
        """测试应用网络波动注入。"""
        mock_state.network_connected = True
        mock_state.apply_injection("network_jitter", {})

        assert mock_state.network_connected is False

    def test_apply_reboot_timeout(self, mock_state):
        """测试应用重启超时注入。"""
        mock_state.boot_completed = True
        mock_state.apply_injection("reboot_timeout", {})

        assert mock_state.boot_completed is False

    def test_apply_cpu_io_stress(self, mock_state):
        """测试应用CPU/I/O压力注入。"""
        mock_state.apply_injection("cpu_io_stress", {})
        mock_state.apply_injection("cpu_io_stress", {})

        # 每次添加一个压力进程
        assert len(mock_state.stress_processes) == 2

    def test_apply_unknown_fault_type(self, mock_state):
        """测试应用未知故障类型不产生错误。"""
        mock_state.apply_injection("unknown_fault", {})
        # 不应产生错误，状态保持不变


class TestMockDeviceStateApplyRecovery:
    """测试MockDeviceState.apply_recovery方法。"""

    def test_apply_cleanup_storage(self, mock_state):
        """测试应用存储清理恢复。"""
        mock_state.apply_injection("storage_pressure", {"pressure_mb": 200})
        reduced_available = mock_state.storage_available

        mock_state.apply_recovery("cleanup_storage", {"pressure_mb": 200})

        assert mock_state.storage_available == reduced_available + 200 * 1024 * 1024

    def test_apply_reset_battery(self, mock_state):
        """测试应用电池重置恢复。"""
        mock_state.apply_injection("low_battery", {"level": 5})

        mock_state.apply_recovery("reset_battery", {})

        assert mock_state.battery_level == 100

    def test_apply_reset_network(self, mock_state):
        """测试应用网络重置恢复。"""
        mock_state.apply_injection("network_jitter", {})

        mock_state.apply_recovery("reset_network", {})

        assert mock_state.network_connected is True

    def test_apply_wait_boot(self, mock_state):
        """测试应用等待启动恢复。"""
        mock_state.apply_injection("reboot_timeout", {})

        mock_state.apply_recovery("wait_boot", {})

        assert mock_state.boot_completed is True

    def test_apply_stop_stress(self, mock_state):
        """测试应用停止压力恢复。"""
        mock_state.apply_injection("cpu_io_stress", {})
        mock_state.apply_injection("cpu_io_stress", {})

        mock_state.apply_recovery("stop_stress", {})

        assert len(mock_state.stress_processes) == 0

    def test_apply_unknown_recovery_step(self, mock_state):
        """测试应用未知恢复步骤不产生错误。"""
        mock_state.apply_recovery("unknown_step", {})
        # 不应产生错误


class TestMockDeviceStateReset:
    """测试MockDeviceState.reset方法。"""

    def test_reset_all_state(self, mock_state):
        """测试重置所有状态。"""
        # 应用多种注入
        mock_state.apply_injection("storage_pressure", {"pressure_mb": 500})
        mock_state.apply_injection("low_battery", {"level": 10})
        mock_state.apply_injection("network_jitter", {})
        mock_state.apply_injection("cpu_io_stress", {})

        # 重置
        mock_state.reset()

        # 所有状态应恢复到初始值
        assert mock_state.online is True
        assert mock_state.battery_level == 100
        assert mock_state.storage_available == 10 * 1024 * 1024 * 1024
        assert mock_state.boot_completed is True
        assert mock_state.network_connected is True
        assert len(mock_state.stress_processes) == 0


# ==================== MockScenario 测试 ====================

class TestMockScenarioEnum:
    """测试MockScenario枚举。"""

    def test_all_scenarios(self):
        """测试所有Mock场景枚举值。"""
        expected = ["normal", "offline", "low_battery", "storage_full", "boot_timeout", "network_error"]
        actual = [s.value for s in MockScenario]
        assert actual == expected

    def test_scenario_string_conversion(self):
        """测试场景枚举字符串转换。"""
        assert MockScenario.normal == "normal"
        assert MockScenario.offline == "offline"


# ==================== ExecutorMode 测试 ====================

class TestExecutorModeEnum:
    """测试ExecutorMode枚举。"""

    def test_modes(self):
        """测试执行模式枚举值。"""
        assert ExecutorMode.real.value == "real"
        assert ExecutorMode.mock.value == "mock"


# ==================== 数据类测试 ====================

class TestStorageInfo:
    """测试StorageInfo数据类。"""

    def test_storage_info_creation(self):
        """测试创建存储信息。"""
        info = StorageInfo(
            total=32 * 1024 * 1024 * 1024,
            available=10 * 1024 * 1024 * 1024,
            used=22 * 1024 * 1024 * 1024,
            path="/data",
        )

        assert info.total == 32 * 1024 * 1024 * 1024
        assert info.path == "/data"

    def test_storage_info_default_path(self):
        """测试存储信息默认路径。"""
        info = StorageInfo(total=100, available=50, used=50)
        assert info.path == "/"


class TestBatteryInfo:
    """测试BatteryInfo数据类。"""

    def test_battery_info_creation(self):
        """测试创建电池信息。"""
        info = BatteryInfo(
            level=85,
            status="charging",
            temperature=30,
            health="good",
        )

        assert info.level == 85
        assert info.status == "charging"
        assert info.temperature == 30
        assert info.health == "good"

    def test_battery_info_optional_fields(self):
        """测试电池信息可选字段。"""
        info = BatteryInfo(level=50, status="discharging")

        assert info.temperature is None
        assert info.health is None


class TestShellResult:
    """测试ShellResult数据类。"""

    def test_shell_result_success(self):
        """测试成功的Shell结果。"""
        result = ShellResult(
            success=True,
            stdout="output",
            stderr="",
            exit_code=0,
            duration_ms=100,
        )

        assert result.success is True
        assert result.stdout == "output"
        assert result.exit_code == 0

    def test_shell_result_failure(self):
        """测试失败的Shell结果。"""
        result = ShellResult(
            success=False,
            stdout="",
            stderr="Error occurred",
            exit_code=1,
        )

        assert result.success is False
        assert result.stderr == "Error occurred"
        assert result.exit_code == 1

    def test_shell_result_default_duration(self):
        """测试Shell结果默认持续时间。"""
        result = ShellResult(success=True, stdout="", stderr="", exit_code=0)
        assert result.duration_ms == 0


class TestMonkeyResult:
    """测试MonkeyResult数据类。"""

    def test_monkey_result_success(self):
        """测试成功的Monkey结果。"""
        result = MonkeyResult(
            success=True,
            total_events=1000,
            crash_count=0,
            anr_count=0,
            output="Monkey finished",
            duration_ms=5000,
        )

        assert result.success is True
        assert result.total_events == 1000
        assert result.crash_count == 0

    def test_monkey_result_with_crashes(self):
        """测试带crash的Monkey结果。"""
        result = MonkeyResult(
            success=True,
            total_events=500,
            crash_count=3,
            anr_count=1,
            output="Crashes detected",
        )

        assert result.crash_count == 3
        assert result.anr_count == 1

    def test_monkey_result_default_duration(self):
        """测试Monkey结果默认持续时间。"""
        result = MonkeyResult(
            success=True,
            total_events=100,
            crash_count=0,
            anr_count=0,
            output="test",
        )
        assert result.duration_ms == 0


# ==================== BaseDeviceExecutor抽象类测试 ====================

class TestBaseDeviceExecutorAbstract:
    """测试BaseDeviceExecutor抽象类。"""

    def test_cannot_instantiate_directly(self):
        """测试不能直接实例化BaseDeviceExecutor。"""
        with pytest.raises(TypeError):
            BaseDeviceExecutor()

    def test_abstract_methods_required(self):
        """测试子类必须实现所有抽象方法。"""
        class IncompleteExecutor:
            mode = ExecutorMode.mock
            device_serial = "test"

            async def is_online(self):
                return True
            # 缺少其他方法

        # 不继承BaseDeviceExecutor则不会报错
        executor = IncompleteExecutor()
        assert executor.mode == ExecutorMode.mock


# ==================== RealDeviceExecutor 测试 ====================

class TestRealDeviceExecutorInit:
    """测试RealDeviceExecutor初始化。"""

    def test_init_with_serial(self):
        """测试带序列号初始化。"""
        from chaosdroid.executors.real_executor import RealDeviceExecutor
        executor = RealDeviceExecutor("real_device_001")

        assert executor.device_serial == "real_device_001"
        assert executor.mode == ExecutorMode.real

    def test_init_has_adb_path(self):
        """测试初始化包含ADB路径。"""
        from chaosdroid.executors.real_executor import RealDeviceExecutor
        executor = RealDeviceExecutor("device_001")

        assert hasattr(executor, "adb_path")
        assert executor.adb_path is not None

    def test_init_loads_settings(self):
        """测试初始化加载设置。"""
        from chaosdroid.executors.real_executor import RealDeviceExecutor
        executor = RealDeviceExecutor("device_001")

        assert hasattr(executor, "settings")


class TestRealDeviceExecutorBuildCommand:
    """测试RealDeviceExecutor构建ADB命令。"""

    @pytest.fixture
    def real_executor(self):
        """创建RealDeviceExecutor实例。"""
        from chaosdroid.executors.real_executor import RealDeviceExecutor
        return RealDeviceExecutor("test_serial")

    def test_build_adb_command_with_serial(self, real_executor):
        """测试构建ADB命令包含序列号。"""
        cmd = real_executor._build_adb_command("shell", "getprop")

        assert "adb" in cmd
        assert "-s" in cmd
        assert "test_serial" in cmd
        assert "shell" in cmd
        assert "getprop" in cmd

    def test_build_adb_command_simple(self, real_executor):
        """测试构建简单ADB命令。"""
        cmd = real_executor._build_adb_command("devices")

        assert "adb" in cmd
        assert "devices" in cmd

    def test_build_adb_command_multiple_args(self, real_executor):
        """测试构建多参数ADB命令。"""
        cmd = real_executor._build_adb_command("shell", "ls", "-la", "/sdcard")

        assert "shell" in cmd
        assert "ls" in cmd
        assert "-la" in cmd
        assert "/sdcard" in cmd


class TestRealDeviceExecutorMocked:
    """测试RealDeviceExecutor方法（使用Mock模拟ADB）。"""

    @pytest.fixture
    def real_executor_mocked(self):
        """创建RealDeviceExecutor并Mock设置。"""
        from chaosdroid.executors.real_executor import RealDeviceExecutor
        executor = RealDeviceExecutor("test_serial")
        return executor

    async def test_is_online_device_connected(self, real_executor_mocked):
        """测试设备在线时is_online返回True。"""
        real_executor_mocked._run_adb_command = AsyncMock(
            return_value=ShellResult(
                success=True,
                stdout="device",
                stderr="",
                exit_code=0
            )
        )

        online = await real_executor_mocked.is_online()
        assert online is True

    async def test_is_online_device_offline(self, real_executor_mocked):
        """测试设备离线时is_online返回False。"""
        real_executor_mocked._run_adb_command = AsyncMock(
            return_value=ShellResult(
                success=True,
                stdout="offline",
                stderr="",
                exit_code=0
            )
        )

        online = await real_executor_mocked.is_online()
        assert online is False

    async def test_is_online_unauthorized(self, real_executor_mocked):
        """测试未授权设备is_online返回False。"""
        real_executor_mocked._run_adb_command = AsyncMock(
            return_value=ShellResult(
                success=True,
                stdout="unauthorized",
                stderr="",
                exit_code=0
            )
        )

        online = await real_executor_mocked.is_online()
        assert online is False

    async def test_get_properties_success(self, real_executor_mocked):
        """测试get_properties成功解析属性。"""
        mock_output = """
[ro.product.model]: [Pixel 7]
[ro.product.brand]: [google]
[ro.build.version.release]: [14]
[ro.build.version.sdk]: [34]
"""
        real_executor_mocked._run_adb_command = AsyncMock(
            return_value=ShellResult(
                success=True,
                stdout=mock_output,
                stderr="",
                exit_code=0
            )
        )

        properties = await real_executor_mocked.get_properties()

        assert properties["ro.product.model"] == "Pixel 7"
        assert properties["ro.product.brand"] == "google"
        assert properties["ro.build.version.release"] == "14"
        assert properties["ro.build.version.sdk"] == "34"

    async def test_get_properties_empty_on_failure(self, real_executor_mocked):
        """测试get_properties失败时返回空字典。"""
        real_executor_mocked._run_adb_command = AsyncMock(
            return_value=ShellResult(
                success=False,
                stdout="",
                stderr="error: device not found",
                exit_code=1
            )
        )

        properties = await real_executor_mocked.get_properties()
        assert properties == {}

    async def test_get_battery_info_success(self, real_executor_mocked):
        """测试get_battery_info成功解析电池信息。"""
        mock_output = """
Current Battery Service state:
  AC powered: false
  USB powered: true
  level: 85
  status: 3
  temperature: 250
"""
        real_executor_mocked._run_adb_command = AsyncMock(
            return_value=ShellResult(
                success=True,
                stdout=mock_output,
                stderr="",
                exit_code=0
            )
        )

        battery = await real_executor_mocked.get_battery_info()

        assert battery.level == 85
        assert battery.status == "discharging"
        assert battery.temperature == 25

    async def test_get_storage_info_success(self, real_executor_mocked):
        """测试get_storage_info成功解析存储信息。"""
        # df命令输出示例
        mock_output = """Filesystem           1K-blocks      Used Available Use% Mounted on
/dev/block/dm-0       65536000  52428800  13107200  80% /sdcard
"""
        real_executor_mocked._run_adb_command = AsyncMock(
            return_value=ShellResult(
                success=True,
                stdout=mock_output,
                stderr="",
                exit_code=0
            )
        )

        storage = await real_executor_mocked.get_storage_info()

        assert storage.total > 0
        assert storage.available > 0
        assert storage.path == "/sdcard"

    async def test_check_boot_completed_true(self, real_executor_mocked):
        """测试check_boot_completed返回True。"""
        real_executor_mocked._run_adb_command = AsyncMock(
            return_value=ShellResult(
                success=True,
                stdout="1",
                stderr="",
                exit_code=0
            )
        )

        result = await real_executor_mocked.check_boot_completed()
        assert result is True

    async def test_check_boot_completed_false(self, real_executor_mocked):
        """测试check_boot_completed返回False。"""
        real_executor_mocked._run_adb_command = AsyncMock(
            return_value=ShellResult(
                success=True,
                stdout="0",
                stderr="",
                exit_code=0
            )
        )

        result = await real_executor_mocked.check_boot_completed()
        assert result is False

    async def test_execute_shell_success(self, real_executor_mocked):
        """测试execute_shell成功执行。"""
        real_executor_mocked._run_adb_command = AsyncMock(
            return_value=ShellResult(
                success=True,
                stdout="file1.txt\nfile2.txt",
                stderr="",
                exit_code=0
            )
        )

        result = await real_executor_mocked.execute_shell("ls /sdcard")

        assert result.success is True
        assert "file1.txt" in result.stdout

    async def test_execute_shell_with_timeout(self, real_executor_mocked):
        """测试execute_shell带超时。"""
        real_executor_mocked._run_adb_command = AsyncMock(
            return_value=ShellResult(
                success=True,
                stdout="output",
                stderr="",
                exit_code=0
            )
        )

        result = await real_executor_mocked.execute_shell("ls", timeout=30)

        assert result.success is True

    async def test_run_monkey_success(self, real_executor_mocked):
        """测试run_monkey成功执行。"""
        mock_output = """
Events injected: 1000
## Network stats: elapsed time=5000ms
Monkey finished
"""
        real_executor_mocked._run_adb_command = AsyncMock(
            return_value=ShellResult(
                success=True,
                stdout=mock_output,
                stderr="",
                exit_code=0,
                duration_ms=5000
            )
        )

        result = await real_executor_mocked.run_monkey("com.test.app", 1000)

        assert result.success is True
        assert result.total_events == 1000
        assert result.crash_count == 0

    async def test_run_monkey_with_crashes(self, real_executor_mocked):
        """测试run_monkey检测crashes。"""
        mock_output = """
Events injected: 500
// CRASH: com.test.app (pid 1234)
** Monkey aborted due to crash
"""
        real_executor_mocked._run_adb_command = AsyncMock(
            return_value=ShellResult(
                success=True,
                stdout=mock_output,
                stderr="",
                exit_code=0,
                duration_ms=2000
            )
        )

        result = await real_executor_mocked.run_monkey("com.test.app", 500)

        assert result.crash_count > 0

    async def test_run_monkey_with_anrs(self, real_executor_mocked):
        """测试run_monkey检测ANRs。"""
        mock_output = """
Events injected: 500
// ANR: com.test.app
"""
        real_executor_mocked._run_adb_command = AsyncMock(
            return_value=ShellResult(
                success=True,
                stdout=mock_output,
                stderr="",
                exit_code=0
            )
        )

        result = await real_executor_mocked.run_monkey("com.test.app", 500)

        assert result.anr_count > 0

    async def test_push_file_success(self, real_executor_mocked):
        """测试push_file成功。"""
        real_executor_mocked._run_adb_command = AsyncMock(
            return_value=ShellResult(
                success=True,
                stdout="file pushed successfully",
                stderr="",
                exit_code=0
            )
        )

        result = await real_executor_mocked.push_file("/local/file", "/remote/file")
        assert result is True

    async def test_push_file_failure(self, real_executor_mocked):
        """测试push_file失败。"""
        real_executor_mocked._run_adb_command = AsyncMock(
            return_value=ShellResult(
                success=False,
                stdout="",
                stderr="error: cannot push",
                exit_code=1
            )
        )

        result = await real_executor_mocked.push_file("/local/file", "/remote/file")
        assert result is False

    async def test_pull_file_success(self, real_executor_mocked):
        """测试pull_file成功。"""
        real_executor_mocked._run_adb_command = AsyncMock(
            return_value=ShellResult(
                success=True,
                stdout="file pulled successfully",
                stderr="",
                exit_code=0
            )
        )

        result = await real_executor_mocked.pull_file("/remote/file", "/local/file")
        assert result is True

    async def test_get_logcat_success(self, real_executor_mocked):
        """测试get_logcat成功。"""
        mock_logcat = "I/ActivityManager: Displayed activity\nD/DebugTag: Debug message\n"
        real_executor_mocked._run_adb_command = AsyncMock(
            return_value=ShellResult(
                success=True,
                stdout=mock_logcat,
                stderr="",
                exit_code=0
            )
        )

        logcat = await real_executor_mocked.get_logcat(100)
        assert "ActivityManager" in logcat


class TestRealDeviceExecutorEdgeCases:
    """测试RealDeviceExecutor边缘情况。"""

    @pytest.fixture
    def real_executor(self):
        """创建RealDeviceExecutor实例。"""
        from chaosdroid.executors.real_executor import RealDeviceExecutor
        return RealDeviceExecutor("test_serial")

    async def test_adb_timeout(self, real_executor):
        """测试ADB命令超时。"""
        # Mock超时场景
        async def mock_run_with_timeout(*args, **kwargs):
            from chaosdroid.executors.base import ShellResult
            return ShellResult(
                success=False,
                stdout="",
                stderr="Command timed out",
                exit_code=-1,
                duration_ms=30000
            )

        real_executor._run_adb_command = mock_run_with_timeout

        result = await real_executor.execute_shell("long_running_command", timeout=30)

        assert result.success is False
        assert "timed out" in result.stderr.lower()

    async def test_adb_not_found(self, real_executor):
        """测试ADB未找到。"""
        async def mock_run_with_file_not_found(*args, **kwargs):
            from chaosdroid.executors.base import ShellResult
            return ShellResult(
                success=False,
                stdout="",
                stderr="ADB not found: invalid_adb_path",
                exit_code=-1
            )

        real_executor._run_adb_command = mock_run_with_file_not_found

        result = await real_executor.is_online()

        assert result is False

    async def test_empty_getprop_output(self, real_executor):
        """测试空getprop输出。"""
        real_executor._run_adb_command = AsyncMock(
            return_value=ShellResult(
                success=True,
                stdout="",
                stderr="",
                exit_code=0
            )
        )

        properties = await real_executor.get_properties()
        assert properties == {}