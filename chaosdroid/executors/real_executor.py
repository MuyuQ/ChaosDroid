"""真实设备执行器."""
import asyncio
import subprocess
import shutil
from typing import Dict, Any, Optional, List

from chaosdroid.config.settings import get_settings
from chaosdroid.executors.base import (
    BaseDeviceExecutor,
    ExecutorMode,
    StorageInfo,
    BatteryInfo,
    ShellResult,
    MonkeyResult
)


class RealDeviceExecutor(BaseDeviceExecutor):
    """真实设备执行器

    通过ADB与真实Android设备通信。
    """

    mode = ExecutorMode.real

    def __init__(self, serial: str):
        self.device_serial = serial
        self.settings = get_settings()
        self.adb_path = self.settings.adb_path

    def _build_adb_command(self, *args) -> List[str]:
        """构建ADB命令."""
        cmd = [self.adb_path]
        if self.device_serial:
            cmd.extend(["-s", self.device_serial])
        cmd.extend(args)
        return cmd

    async def _run_adb_command(self, *args, timeout: int = 30) -> ShellResult:
        """执行ADB命令."""
        cmd = self._build_adb_command(*args)
        started_at = asyncio.get_event_loop().time()

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                return ShellResult(
                    success=False,
                    stdout="",
                    stderr="Command timed out",
                    exit_code=-1,
                    duration_ms=timeout * 1000
                )

            duration_ms = int((asyncio.get_event_loop().time() - started_at) * 1000)

            return ShellResult(
                success=process.returncode == 0,
                stdout=stdout.decode("utf-8", errors="replace"),
                stderr=stderr.decode("utf-8", errors="replace"),
                exit_code=process.returncode or 0,
                duration_ms=duration_ms
            )

        except FileNotFoundError:
            return ShellResult(
                success=False,
                stdout="",
                stderr=f"ADB not found: {self.adb_path}",
                exit_code=-1
            )
        except Exception as e:
            return ShellResult(
                success=False,
                stdout="",
                stderr=str(e),
                exit_code=-1
            )

    async def is_online(self) -> bool:
        """检查设备是否在线."""
        result = await self._run_adb_command("get-state", timeout=5)
        return result.success and "device" in result.stdout.strip()

    async def get_properties(self) -> Dict[str, str]:
        """获取设备属性."""
        result = await self._run_adb_command("shell", "getprop", timeout=30)

        if not result.success:
            return {}

        properties = {}
        for line in result.stdout.strip().split("\n"):
            if line.startswith("[") and "]: [" in line:
                key_end = line.index("]: [")
                key = line[1:key_end]
                value_start = key_end + 4
                value_end = line.rindex("]")
                value = line[value_start:value_end]
                properties[key] = value

        return properties

    async def get_storage_info(self) -> StorageInfo:
        """获取存储信息."""
        result = await self._run_adb_command(
            "shell", "df", "/sdcard", timeout=30
        )

        if not result.success:
            return StorageInfo(total=0, available=0, used=0, path="/sdcard")

        # 解析df输出
        lines = result.stdout.strip().split("\n")
        if len(lines) >= 2:
            parts = lines[1].split()
            if len(parts) >= 4:
                total = int(parts[1]) * 1024  # 转换为字节
                used = int(parts[2]) * 1024
                available = int(parts[3]) * 1024
                return StorageInfo(
                    total=total,
                    available=available,
                    used=used,
                    path=parts[5] if len(parts) > 5 else "/sdcard"
                )

        return StorageInfo(total=0, available=0, used=0, path="/sdcard")

    async def get_battery_info(self) -> BatteryInfo:
        """获取电池信息."""
        result = await self._run_adb_command(
            "shell", "dumpsys", "battery", timeout=30
        )

        level = 0
        status = "unknown"
        temperature = None

        if result.success:
            for line in result.stdout.split("\n"):
                line = line.strip()
                if line.startswith("level:"):
                    level = int(line.split(":")[1].strip())
                elif line.startswith("status:"):
                    status_codes = {
                        "1": "unknown", "2": "charging", "3": "discharging",
                        "4": "not charging", "5": "full"
                    }
                    code = line.split(":")[1].strip()
                    status = status_codes.get(code, "unknown")
                elif line.startswith("temperature:"):
                    temp = int(line.split(":")[1].strip())
                    temperature = temp // 10  # 转换为摄氏度

        return BatteryInfo(
            level=level,
            status=status,
            temperature=temperature
        )

    async def execute_shell(self, cmd: str, timeout: int = 30) -> ShellResult:
        """执行Shell命令."""
        return await self._run_adb_command("shell", cmd, timeout=timeout)

    async def push_file(self, local_path: str, remote_path: str) -> bool:
        """推送文件到设备."""
        result = await self._run_adb_command(
            "push", local_path, remote_path, timeout=120
        )
        return result.success

    async def pull_file(self, remote_path: str, local_path: str) -> bool:
        """从设备拉取文件."""
        result = await self._run_adb_command(
            "pull", remote_path, local_path, timeout=120
        )
        return result.success

    async def run_monkey(
        self,
        package: str,
        count: int,
        options: Dict[str, Any] = None
    ) -> MonkeyResult:
        """运行Monkey测试."""
        options = options or {}
        seed = options.get("seed", "")
        throttle = options.get("throttle", 50)

        cmd_parts = [
            "shell", "monkey",
            "-p", package,
            "-v", str(count),
        ]

        if seed:
            cmd_parts.extend(["-s", str(seed)])
        if throttle:
            cmd_parts.extend(["--throttle", str(throttle)])

        result = await self._run_adb_command(
            *cmd_parts,
            timeout=count * throttle // 1000 + 60
        )

        # 解析monkey输出
        crash_count = 0
        anr_count = 0

        if result.stdout:
            crash_count = result.stdout.count("// CRASH:")
            anr_count = result.stdout.count("// ANR:")

        return MonkeyResult(
            success=result.success and crash_count == 0 and anr_count == 0,
            total_events=count,
            crash_count=crash_count,
            anr_count=anr_count,
            output=result.stdout,
            duration_ms=result.duration_ms
        )

    async def reboot(self, wait_timeout: int = 120) -> bool:
        """重启设备并等待."""
        # 发送重启命令
        result = await self._run_adb_command("reboot", timeout=10)
        if not result.success:
            return False

        # 等待设备离线
        await asyncio.sleep(5)

        # 等待设备重新上线
        for _ in range(wait_timeout // 5):
            await asyncio.sleep(5)
            if await self.is_online():
                # 等待boot完成
                return await self.wait_for_boot(timeout=60)

        return False

    async def wait_for_boot(self, timeout: int = 60) -> bool:
        """等待设备启动完成."""
        for _ in range(timeout // 2):
            result = await self._run_adb_command(
                "shell", "getprop", "sys.boot_completed",
                timeout=5
            )
            if result.success and result.stdout.strip() == "1":
                return True
            await asyncio.sleep(2)
        return False

    async def check_boot_completed(self) -> bool:
        """检查boot是否完成."""
        result = await self._run_adb_command(
            "shell", "getprop", "sys.boot_completed",
            timeout=10
        )
        return result.success and result.stdout.strip() == "1"

    async def get_logcat(self, lines: int = 1000) -> str:
        """获取logcat日志."""
        result = await self._run_adb_command(
            "shell", "logcat", "-d", "-t", str(lines),
            timeout=60
        )
        return result.stdout if result.success else ""