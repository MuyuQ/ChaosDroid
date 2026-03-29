"""Mock设备执行器."""
import asyncio
import random
from typing import Dict, Any, Optional, List

from chaosdroid.executors.base import (
    BaseDeviceExecutor,
    ExecutorMode,
    MockScenario,
    StorageInfo,
    BatteryInfo,
    ShellResult,
    MonkeyResult
)


class MockDeviceState:
    """Mock设备状态管理"""

    def __init__(self, serial: str, scenario: MockScenario = MockScenario.normal):
        self.serial = serial
        self.scenario = scenario
        self.online = True
        self.battery_level = 100
        self.storage_total = 32 * 1024 * 1024 * 1024  # 32GB
        self.storage_available = 10 * 1024 * 1024 * 1024  # 10GB
        self.boot_completed = True
        self.network_connected = True
        self.stress_processes: List[str] = []
        self.properties: Dict[str, str] = {
            "ro.product.model": "Mock Device",
            "ro.product.brand": "MockBrand",
            "ro.build.version.release": "14",
            "ro.build.version.sdk": "34",
        }

        # 根据场景初始化状态
        self._apply_scenario(scenario)

    def _apply_scenario(self, scenario: MockScenario):
        """根据场景设置初始状态"""
        if scenario == MockScenario.offline:
            self.online = False
        elif scenario == MockScenario.low_battery:
            self.battery_level = 15
        elif scenario == MockScenario.storage_full:
            self.storage_available = 50 * 1024 * 1024  # 50MB
        elif scenario == MockScenario.boot_timeout:
            self.boot_completed = False
        elif scenario == MockScenario.network_error:
            self.network_connected = False

    def apply_injection(self, fault_type: str, params: Dict[str, Any]):
        """应用故障注入"""
        if fault_type == "storage_pressure":
            pressure_mb = params.get("pressure_mb", 1000)
            pressure_bytes = pressure_mb * 1024 * 1024
            self.storage_available = max(0, self.storage_available - pressure_bytes)
        elif fault_type == "low_battery":
            self.battery_level = params.get("level", 10)
        elif fault_type == "network_jitter":
            self.network_connected = False
        elif fault_type == "reboot_timeout":
            self.boot_completed = False
        elif fault_type == "cpu_io_stress":
            self.stress_processes.append(f"stress_process_{len(self.stress_processes)}")

    def apply_recovery(self, step: str, params: Dict[str, Any] = None):
        """应用恢复操作"""
        if step == "cleanup_storage":
            pressure_mb = (params or {}).get("pressure_mb", 1000)
            self.storage_available += pressure_mb * 1024 * 1024
        elif step == "reset_battery":
            self.battery_level = 100
        elif step == "reset_network":
            self.network_connected = True
        elif step == "wait_boot":
            self.boot_completed = True
        elif step == "stop_stress":
            self.stress_processes.clear()

    def reset(self):
        """重置到初始状态"""
        self.online = True
        self.battery_level = 100
        self.storage_available = 10 * 1024 * 1024 * 1024
        self.boot_completed = True
        self.network_connected = True
        self.stress_processes.clear()


class MockDeviceExecutor(BaseDeviceExecutor):
    """Mock设备执行器"""

    mode = ExecutorMode.mock

    def __init__(self, serial: str, scenario: MockScenario = MockScenario.normal):
        self.device_serial = serial
        self.state = MockDeviceState(serial, scenario)

    async def _simulate_delay(self, min_ms: int = 100, max_ms: int = 500):
        """模拟操作延迟"""
        delay = random.uniform(min_ms / 1000, max_ms / 1000)
        await asyncio.sleep(delay)

    async def is_online(self) -> bool:
        """检查设备是否在线"""
        await self._simulate_delay(50, 100)
        return self.state.online

    async def get_properties(self) -> Dict[str, str]:
        """获取设备属性"""
        await self._simulate_delay()
        if not self.state.online:
            return {}
        return self.state.properties.copy()

    async def get_storage_info(self) -> StorageInfo:
        """获取存储信息"""
        await self._simulate_delay()
        return StorageInfo(
            total=self.state.storage_total,
            available=self.state.storage_available,
            used=self.state.storage_total - self.state.storage_available,
            path="/"
        )

    async def get_battery_info(self) -> BatteryInfo:
        """获取电池信息"""
        await self._simulate_delay()
        return BatteryInfo(
            level=self.state.battery_level,
            status="discharging",
            temperature=25,
            health="good"
        )

    async def execute_shell(self, cmd: str, timeout: int = 30) -> ShellResult:
        """执行Shell命令"""
        await self._simulate_delay()

        if not self.state.online:
            return ShellResult(
                success=False,
                stdout="",
                stderr="Device offline",
                exit_code=-1
            )

        # 处理特殊命令
        if cmd.startswith("getprop"):
            prop = cmd.split()[-1] if len(cmd.split()) > 1 else ""
            if prop == "sys.boot_completed":
                return ShellResult(
                    success=True,
                    stdout="1" if self.state.boot_completed else "0",
                    stderr="",
                    exit_code=0
                )
            return ShellResult(
                success=True,
                stdout=self.state.properties.get(prop, ""),
                stderr="",
                exit_code=0
            )

        if cmd.startswith("dumpsys battery"):
            return ShellResult(
                success=True,
                stdout=f"level: {self.state.battery_level}",
                stderr="",
                exit_code=0
            )

        # 默认成功执行
        return ShellResult(
            success=True,
            stdout="mock_output",
            stderr="",
            exit_code=0
        )

    async def push_file(self, local_path: str, remote_path: str) -> bool:
        """推送文件"""
        await self._simulate_delay(200, 500)
        return self.state.online

    async def pull_file(self, remote_path: str, local_path: str) -> bool:
        """拉取文件"""
        await self._simulate_delay(200, 500)
        return self.state.online

    async def run_monkey(self, package: str, count: int, options: Dict[str, Any] = None) -> MonkeyResult:
        """运行Monkey测试"""
        await self._simulate_delay(1000, 3000)

        if not self.state.online:
            return MonkeyResult(
                success=False,
                total_events=0,
                crash_count=0,
                anr_count=0,
                output="Device offline"
            )

        # 根据场景生成不同结果
        crash_count = 0
        anr_count = 0

        if self.state.scenario == MockScenario.network_error:
            crash_count = random.randint(1, 3)

        return MonkeyResult(
            success=True,
            total_events=count,
            crash_count=crash_count,
            anr_count=anr_count,
            output=f"Monkey completed with {count} events",
            duration_ms=random.randint(1000, 5000)
        )

    async def reboot(self, wait_timeout: int = 120) -> bool:
        """重启设备"""
        await self._simulate_delay(500, 1000)

        if not self.state.online:
            return False

        # 模拟重启过程
        self.state.boot_completed = False
        await asyncio.sleep(2)  # 模拟重启时间

        # 根据场景决定是否成功启动
        if self.state.scenario == MockScenario.boot_timeout:
            return False

        self.state.boot_completed = True
        return True

    async def wait_for_boot(self, timeout: int = 60) -> bool:
        """等待设备启动完成"""
        await asyncio.sleep(1)

        if self.state.scenario == MockScenario.boot_timeout:
            return False

        return self.state.boot_completed

    async def check_boot_completed(self) -> bool:
        """检查boot是否完成"""
        return self.state.boot_completed

    async def get_logcat(self, lines: int = 1000) -> str:
        """获取logcat日志"""
        await self._simulate_delay(200, 500)

        if not self.state.online:
            return ""

        # 生成模拟日志
        log_lines = []
        for i in range(min(lines, 100)):
            log_lines.append(f"Mock log line {i}")
        return "\n".join(log_lines)

    def get_state(self) -> MockDeviceState:
        """获取设备状态对象（用于注入器操作）"""
        return self.state