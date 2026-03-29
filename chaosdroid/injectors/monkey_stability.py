"""Monkey稳定性注入器."""
import asyncio
import random
import re
from typing import Dict, Any

from chaosdroid.injectors.base import (
    BaseInjector,
    FaultType,
    RiskLevel,
    InjectContext,
    InjectResult
)


class MonkeyStabilityInjector(BaseInjector):
    """Monkey稳定性注入器

    启动monkey测试，采集输出统计crash/ANR。
    """

    fault_type = FaultType.monkey_stability
    risk_level = RiskLevel.medium

    def __init__(self):
        self.package: str = ""
        self.event_count: int = 1000
        self.seed: int = 0
        self.throttle_ms: int = 50
        self.options: Dict[str, Any] = {}

    async def prepare(self, context: InjectContext) -> bool:
        """准备注入环境"""
        executor = context.executor
        fault_profile = context.fault_profile

        # 获取monkey参数
        params = fault_profile.get("parameters", {})
        self.package = params.get("package", "")
        self.event_count = params.get("event_count", 1000)
        self.seed = params.get("seed", random.randint(1, 10000))
        self.throttle_ms = params.get("throttle_ms", 50)
        self.options = params.get("options", {})

        # 检查设备在线
        online = await executor.is_online()
        if not online:
            return False

        # 如果指定了包名，检查包是否存在
        if self.package:
            result = await executor.execute_shell(f"pm list packages | grep {self.package}", timeout=30)
            if not result.stdout.strip():
                return False

        return True

    async def inject(self, context: InjectContext) -> InjectResult:
        """执行Monkey稳定性注入"""
        executor = context.executor

        # 检查是否是Mock设备
        is_mock = hasattr(executor, 'get_state')
        if is_mock:
            # Mock模式：模拟monkey运行结果
            await asyncio.sleep(random.uniform(2.0, 5.0))

            # 模拟运行monkey
            monkey_result = await executor.run_monkey(
                self.package or "com.mock.package",
                self.event_count,
                {
                    "seed": self.seed,
                    "throttle": self.throttle_ms
                }
            )

            # 分析结果
            crash_count = monkey_result.crash_count
            anr_count = monkey_result.anr_count

            # 判断稳定性（根据配置）
            max_crashes = self.options.get("max_crashes_allowed", 0)
            max_anrs = self.options.get("max_anrs_allowed", 0)

            success = crash_count <= max_crashes and anr_count <= max_anrs

            return InjectResult(
                success=success,
                fault_type=self.fault_type,
                fault_injected=True,
                fault_observed=True,
                message=f"Mock注入: Monkey完成，crash={crash_count}, ANR={anr_count}",
                details={
                    "package": self.package,
                    "event_count": self.event_count,
                    "seed": self.seed,
                    "throttle_ms": self.throttle_ms,
                    "crash_count": crash_count,
                    "anr_count": anr_count,
                    "total_events": monkey_result.total_events,
                    "duration_ms": monkey_result.duration_ms,
                    "stability_passed": success
                },
                cleanup_required=False
            )
        else:
            # Real模式：运行实际monkey
            monkey_result = await executor.run_monkey(
                self.package,
                self.event_count,
                {
                    "seed": self.seed,
                    "throttle": self.throttle_ms
                }
            )

            # 分析结果
            crash_count = self._parse_crashes(monkey_result.output)
            anr_count = self._parse_anrs(monkey_result.output)

            # 判断稳定性
            max_crashes = self.options.get("max_crashes_allowed", 0)
            max_anrs = self.options.get("max_anrs_allowed", 0)

            success = crash_count <= max_crashes and anr_count <= max_anrs

            return InjectResult(
                success=success,
                fault_type=self.fault_type,
                fault_injected=True,
                fault_observed=True,
                message=f"真实模式: Monkey完成，crash={crash_count}, ANR={anr_count}",
                details={
                    "package": self.package,
                    "event_count": self.event_count,
                    "seed": self.seed,
                    "throttle_ms": self.throttle_ms,
                    "crash_count": crash_count,
                    "anr_count": anr_count,
                    "total_events": monkey_result.total_events,
                    "duration_ms": monkey_result.duration_ms,
                    "stability_passed": success,
                    "real_mode": True
                },
                cleanup_required=False
            )

    def _parse_crashes(self, output: str) -> int:
        """解析monkey输出中的crash数量"""
        # 查找crash相关的模式
        crash_patterns = [
            r"// CRASH:",
            r"\*\* Monkey aborted due to crash",
            r"CRASH:\s*\d+"
        ]
        count = 0
        for pattern in crash_patterns:
            matches = re.findall(pattern, output)
            count += len(matches)
        return count

    def _parse_anrs(self, output: str) -> int:
        """解析monkey输出中的ANR数量"""
        # 查找ANR相关的模式
        anr_patterns = [
            r"// ANR:",
            r"ANR in",
            r"ANR:\s*\d+"
        ]
        count = 0
        for pattern in anr_patterns:
            matches = re.findall(pattern, output)
            count += len(matches)
        return count

    async def cleanup(self, context: InjectContext) -> bool:
        """清理注入"""
        # Monkey测试不需要清理，测试完成后自动结束
        return True


# 注册注入器
from chaosdroid.injectors.base import register_injector
register_injector(MonkeyStabilityInjector())