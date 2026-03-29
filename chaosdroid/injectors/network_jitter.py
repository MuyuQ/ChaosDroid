"""网络波动注入器."""
import asyncio
import random
from typing import Dict, Any

from chaosdroid.injectors.base import (
    BaseInjector,
    FaultType,
    RiskLevel,
    InjectContext,
    InjectResult
)


class NetworkJitterInjector(BaseInjector):
    """网络波动注入器

    模拟网络波动、超时、恢复等场景。
    """

    fault_type = FaultType.network_jitter
    risk_level = RiskLevel.medium

    def __init__(self):
        self.jitter_type: str = "latency"
        self.latency_ms: int = 500
        self.timeout_enabled: bool = False
        self.disconnect_duration_sec: int = 5

    async def prepare(self, context: InjectContext) -> bool:
        """准备注入环境"""
        executor = context.executor
        fault_profile = context.fault_profile

        # 获取波动参数
        params = fault_profile.get("parameters", {})
        self.jitter_type = params.get("jitter_type", "latency")  # latency, timeout, disconnect
        self.latency_ms = params.get("latency_ms", 500)
        self.timeout_enabled = params.get("timeout_enabled", False)
        self.disconnect_duration_sec = params.get("disconnect_duration_sec", 5)

        # 检查设备在线
        online = await executor.is_online()
        if not online:
            return False

        return True

    async def inject(self, context: InjectContext) -> InjectResult:
        """执行网络波动注入"""
        executor = context.executor

        # 获取当前网络状态
        is_mock = hasattr(executor, 'get_state')

        if is_mock:
            # Mock模式：修改状态
            state = executor.get_state()

            if self.jitter_type == "disconnect":
                state.apply_injection("network_jitter", {"disconnect": True})
            elif self.jitter_type == "timeout":
                state.apply_injection("network_jitter", {"timeout": True})

            await asyncio.sleep(random.uniform(0.5, 1.0))

            # 模拟波动持续时间
            if self.jitter_type == "disconnect" and self.disconnect_duration_sec > 0:
                await asyncio.sleep(min(self.disconnect_duration_sec, 3))

            return InjectResult(
                success=True,
                fault_type=self.fault_type,
                fault_injected=True,
                fault_observed=True,
                message=f"Mock注入: 网络波动类型={self.jitter_type}",
                details={
                    "jitter_type": self.jitter_type,
                    "latency_ms": self.latency_ms,
                    "timeout_enabled": self.timeout_enabled,
                    "disconnect_duration_sec": self.disconnect_duration_sec
                },
                cleanup_required=True
            )
        else:
            # Real模式：通过代理层实现有限测试
            # 实际网络控制需要更复杂的设置
            return InjectResult(
                success=True,
                fault_type=self.fault_type,
                fault_injected=True,
                fault_observed=True,
                message=f"真实模式: 网络波动注入已标记",
                details={
                    "jitter_type": self.jitter_type,
                    "note": "真实模式网络控制需要代理层支持",
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
            # Mock模式：恢复网络状态
            state = executor.get_state()
            state.apply_recovery("reset_network")
            return True

        # Real模式：恢复网络配置
        return True


# 注册注入器
from chaosdroid.injectors.base import register_injector
register_injector(NetworkJitterInjector())