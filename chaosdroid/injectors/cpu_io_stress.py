"""CPU/I/O压力注入器."""
import asyncio
import random
from typing import Dict, Any, List

from chaosdroid.injectors.base import (
    BaseInjector,
    FaultType,
    RiskLevel,
    InjectContext,
    InjectResult
)


class CpuIoStressInjector(BaseInjector):
    """CPU/I/O压力注入器

    在设备上启动压力任务，模拟高负载场景。
    """

    fault_type = FaultType.cpu_io_stress
    risk_level = RiskLevel.medium

    def __init__(self):
        self.cpu_load_percent: int = 50
        self.io_enabled: bool = True
        self.duration_sec: int = 60
        self.stress_processes: List[str] = []

    async def prepare(self, context: InjectContext) -> bool:
        """准备注入环境"""
        executor = context.executor
        fault_profile = context.fault_profile

        # 获取压力参数
        params = fault_profile.get("parameters", {})
        self.cpu_load_percent = params.get("cpu_load_percent", 50)
        self.io_enabled = params.get("io_enabled", True)
        self.duration_sec = params.get("duration_sec", 60)

        # 检查设备在线
        online = await executor.is_online()
        if not online:
            return False

        return True

    async def inject(self, context: InjectContext) -> InjectResult:
        """执行CPU/I/O压力注入"""
        executor = context.executor

        # 检查是否是Mock设备
        is_mock = hasattr(executor, 'get_state')
        if is_mock:
            # Mock模式：添加压力进程状态
            state = executor.get_state()
            state.apply_injection("cpu_io_stress", {
                "cpu_load": self.cpu_load_percent,
                "io_enabled": self.io_enabled
            })

            await asyncio.sleep(random.uniform(0.5, 1.0))

            # 模拟运行一段时间
            await asyncio.sleep(min(self.duration_sec, 5))

            return InjectResult(
                success=True,
                fault_type=self.fault_type,
                fault_injected=True,
                fault_observed=True,
                message=f"Mock注入: CPU负载={self.cpu_load_percent}%, I/O={self.io_enabled}",
                details={
                    "cpu_load_percent": self.cpu_load_percent,
                    "io_enabled": self.io_enabled,
                    "duration_sec": self.duration_sec,
                    "stress_processes": len(state.stress_processes)
                },
                cleanup_required=True
            )
        else:
            # Real模式：启动压力任务
            # CPU压力
            cpu_cmd = f"timeout {self.duration_sec} yes > /dev/null"
            result = await executor.execute_shell(cpu_cmd, timeout=self.duration_sec + 10)

            if result.success or result.exit_code == 124:  # timeout正常退出
                self.stress_processes.append("cpu_stress")

            # I/O压力
            if self.io_enabled:
                io_cmd = f"timeout {self.duration_sec} dd if=/dev/zero of=/sdcard/stress_io.dat bs=1M count=100"
                result = await executor.execute_shell(io_cmd, timeout=self.duration_sec + 10)

                if result.success or result.exit_code == 124:
                    self.stress_processes.append("io_stress")

            success = len(self.stress_processes) > 0

            return InjectResult(
                success=success,
                fault_type=self.fault_type,
                fault_injected=success,
                fault_observed=True,
                message=f"真实模式: 启动{len(self.stress_processes)}个压力任务",
                details={
                    "cpu_load_percent": self.cpu_load_percent,
                    "io_enabled": self.io_enabled,
                    "duration_sec": self.duration_sec,
                    "stress_processes": self.stress_processes,
                    "real_mode": True
                },
                cleanup_required=True
            )

    async def cleanup(self, context: InjectContext) -> bool:
        """清理注入"""
        executor = context.executor

        # 检查是否是Mock设备
        is_mock = hasattr(executor, 'get_state')
        if is_mock:
            # Mock模式：清除压力进程状态
            state = executor.get_state()
            state.apply_recovery("stop_stress")
            return True

        # Real模式：停止压力任务
        # 停止yes进程
        result = await executor.execute_shell("pkill -f 'yes > /dev/null'", timeout=10)

        # 清理I/O文件
        result = await executor.execute_shell("rm -f /sdcard/stress_io.dat", timeout=10)

        return True


# 注册注入器
from chaosdroid.injectors.base import register_injector
register_injector(CpuIoStressInjector())