"""恢复服务模块.

提供故障注入后的恢复操作实现。
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from chaosdroid.executors.base import BaseDeviceExecutor

logger = logging.getLogger(__name__)


@dataclass
class RecoveryStep:
    """恢复步骤定义"""
    name: str
    action: str
    params: Dict[str, Any] = field(default_factory=dict)
    timeout_sec: int = 60
    required: bool = True


@dataclass
class RecoveryStepResult:
    """恢复步骤执行结果"""
    step_name: str
    success: bool
    message: str = ""
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RecoveryResult:
    """恢复操作结果"""
    passed: bool
    steps: List[RecoveryStepResult] = field(default_factory=list)
    message: str = ""
    manual_action_required: bool = False


class RecoveryService:
    """恢复服务.

    执行故障注入后的恢复操作，确保设备恢复正常状态。
    """

    # 恢复动作映射
    RECOVERY_ACTIONS = {
        "cleanup_storage": "清理存储压力文件",
        "reset_battery": "重置电池状态",
        "reset_network": "重置网络配置",
        "wait_boot": "等待设备启动完成",
        "stop_stress": "停止压力任务",
        "reboot_device": "重启设备",
        "check_connectivity": "检查设备连通性",
    }

    def __init__(self, recovery_profile: Optional[Dict[str, Any]] = None):
        """初始化恢复服务.

        Args:
            recovery_profile: 恢复配置，包含恢复步骤等信息
        """
        self.recovery_profile = recovery_profile or {}
        self.steps: List[RecoveryStep] = []
        self._parse_recovery_profile()

    def _parse_recovery_profile(self) -> None:
        """解析恢复配置，构建恢复步骤列表."""
        steps_data = self.recovery_profile.get("steps", {})

        if isinstance(steps_data, str):
            import json
            try:
                steps_data = json.loads(steps_data)
            except json.JSONDecodeError:
                steps_data = {}

        # 默认恢复步骤
        default_steps = [
            RecoveryStep(name="cleanup", action="cleanup_injection", required=True),
            RecoveryStep(name="verify", action="check_connectivity", required=True),
        ]

        # 从配置解析步骤
        configured_steps = []
        if isinstance(steps_data, list):
            for i, step_data in enumerate(steps_data):
                if isinstance(step_data, dict):
                    configured_steps.append(RecoveryStep(
                        name=step_data.get("name", f"step_{i}"),
                        action=step_data.get("action", ""),
                        params=step_data.get("params", {}),
                        timeout_sec=step_data.get("timeout_sec", 60),
                        required=step_data.get("required", True),
                    ))

        self.steps = configured_steps or default_steps

    async def execute_recovery_steps(
        self,
        executor: BaseDeviceExecutor,
        context: Dict[str, Any]
    ) -> RecoveryResult:
        """执行恢复步骤.

        Args:
            executor: 设备执行器
            context: 执行上下文

        Returns:
            RecoveryResult: 恢复操作结果
        """
        logger.info(f"开始执行恢复步骤，共{len(self.steps)}步")

        result = RecoveryResult(passed=True)
        injector = context.get("injector")

        try:
            # 1. 首先执行注入器清理
            if injector:
                cleanup_success = await injector.cleanup(context)
                result.steps.append(RecoveryStepResult(
                    step_name="injector_cleanup",
                    success=cleanup_success,
                    message=cleanup_success and "注入器清理成功" or "注入器清理失败"
                ))
                logger.info(f"注入器清理: {'成功' if cleanup_success else '失败'}")

            # 2. 执行配置的恢复步骤
            for step in self.steps:
                step_result = await self._execute_single_step(executor, step, context)
                result.steps.append(step_result)

                if not step_result.success and step.required:
                    logger.warning(f"恢复步骤 {step.name} 失败")
                    # 必要步骤失败时继续尝试后续步骤

            # 3. 最终验证
            final_check = await self._final_verification(executor, context)
            result.steps.append(final_check)

            # 判断整体结果
            failed_required_steps = [
                s for s in result.steps
                if not s.success
            ]

            result.passed = len(failed_required_steps) == 0 and final_check.success
            result.message = result.passed and "恢复成功" or "恢复部分失败"

            # 判断是否需要人工介入
            if not result.passed:
                result.manual_action_required = self.recovery_profile.get(
                    "manual_intervention_allowed", True
                )

        except Exception as e:
            result.passed = False
            result.message = f"恢复过程异常: {str(e)}"
            result.manual_action_required = True
            logger.exception("恢复过程异常")

        logger.info(f"恢复完成: {result.message}")
        return result

    async def _execute_single_step(
        self,
        executor: BaseDeviceExecutor,
        step: RecoveryStep,
        context: Dict[str, Any]
    ) -> RecoveryStepResult:
        """执行单个恢复步骤.

        Args:
            executor: 设备执行器
            step: 恢复步骤定义
            context: 执行上下文

        Returns:
            RecoveryStepResult: 步骤执行结果
        """
        logger.info(f"执行恢复步骤: {step.name} ({step.action})")

        result = RecoveryStepResult(
            step_name=step.name,
            success=False
        )

        try:
            action = step.action
            params = step.params

            if action == "cleanup_storage":
                # 清理存储压力文件
                success = await self._cleanup_storage(executor, params)
                result.success = success
                result.message = success and "存储清理成功" or "存储清理失败"

            elif action == "reset_battery":
                # 重置电池状态（Mock模式）
                success = await self._reset_battery(executor, params)
                result.success = success
                result.message = success and "电池状态重置成功" or "电池状态重置失败"

            elif action == "reset_network":
                # 重置网络配置
                success = await self._reset_network(executor, params)
                result.success = success
                result.message = success and "网络重置成功" or "网络重置失败"

            elif action == "wait_boot":
                # 等待设备启动完成
                success = await self._wait_for_boot(executor, params)
                result.success = success
                result.message = success and "设备启动完成" or "设备启动超时"

            elif action == "stop_stress":
                # 停止压力任务
                success = await self._stop_stress(executor, params)
                result.success = success
                result.message = success and "压力任务已停止" or "停止压力任务失败"

            elif action == "reboot_device":
                # 重启设备
                success = await self._reboot_device(executor, params)
                result.success = success
                result.message = success and "设备重启成功" or "设备重启失败"

            elif action == "check_connectivity":
                # 检查设备连通性
                success = await executor.is_online()
                result.success = success
                result.message = success and "设备在线" or "设备离线"

            elif action == "cleanup_injection":
                # 通用注入清理（由注入器处理）
                result.success = True
                result.message = "已由注入器处理"

            else:
                result.message = f"未知恢复动作: {action}"
                logger.warning(result.message)

        except Exception as e:
            result.success = False
            result.message = f"执行异常: {str(e)}"
            logger.exception(f"恢复步骤 {step.name} 执行异常")

        result.details = {
            "action": step.action,
            "params": step.params,
            "timeout_sec": step.timeout_sec,
        }

        return result

    async def _cleanup_storage(
        self,
        executor: BaseDeviceExecutor,
        params: Dict[str, Any]
    ) -> bool:
        """清理存储压力文件."""
        target_path = params.get("target_path", "/sdcard/chaosdroid_pressure")

        # 检查是否是Mock设备
        if hasattr(executor, 'get_state'):
            state = executor.get_state()
            state.apply_recovery("cleanup_storage", params)
            return True

        # Real模式：删除文件
        result = await executor.execute_shell(f"rm -rf {target_path}", timeout=60)
        return result.success

    async def _reset_battery(
        self,
        executor: BaseDeviceExecutor,
        params: Dict[str, Any]
    ) -> bool:
        """重置电池状态."""
        # Mock模式：恢复电池状态
        if hasattr(executor, 'get_state'):
            state = executor.get_state()
            state.apply_recovery("reset_battery", params)
            return True

        # Real模式：无法软件重置电量，只能等待充电
        return True

    async def _reset_network(
        self,
        executor: BaseDeviceExecutor,
        params: Dict[str, Any]
    ) -> bool:
        """重置网络配置."""
        # Mock模式：恢复网络状态
        if hasattr(executor, 'get_state'):
            state = executor.get_state()
            state.apply_recovery("reset_network", params)
            return True

        # Real模式：重置网络
        result = await executor.execute_shell("svc wifi restart", timeout=30)
        return result.success

    async def _wait_for_boot(
        self,
        executor: BaseDeviceExecutor,
        params: Dict[str, Any]
    ) -> bool:
        """等待设备启动完成."""
        timeout = params.get("timeout_sec", 60)

        # Mock模式：设置boot完成
        if hasattr(executor, 'get_state'):
            state = executor.get_state()
            state.apply_recovery("wait_boot", params)
            return True

        # Real模式：等待boot完成
        return await executor.wait_for_boot(timeout=timeout)

    async def _stop_stress(
        self,
        executor: BaseDeviceExecutor,
        params: Dict[str, Any]
    ) -> bool:
        """停止压力任务."""
        # Mock模式：清除压力进程状态
        if hasattr(executor, 'get_state'):
            state = executor.get_state()
            state.apply_recovery("stop_stress", params)
            return True

        # Real模式：杀死压力进程
        result = await executor.execute_shell("pkill -f 'yes > /dev/null'", timeout=10)
        result2 = await executor.execute_shell("rm -f /sdcard/stress_io.dat", timeout=10)
        return result.success or result2.success

    async def _reboot_device(
        self,
        executor: BaseDeviceExecutor,
        params: Dict[str, Any]
    ) -> bool:
        """重启设备."""
        wait_timeout = params.get("wait_timeout", 120)

        # 执行重启
        return await executor.reboot(wait_timeout=wait_timeout)

    async def _final_verification(
        self,
        executor: BaseDeviceExecutor,
        context: Dict[str, Any]
    ) -> RecoveryStepResult:
        """最终验证.

        检查设备是否恢复到可用状态。
        """
        result = RecoveryStepResult(
            step_name="final_verification",
            success=False
        )

        try:
            # 检查设备在线
            online = await executor.is_online()
            if not online:
                result.message = "设备离线"
                return result

            # 检查boot完成
            boot_completed = await executor.check_boot_completed()
            if not boot_completed:
                result.message = "Boot未完成"
                return result

            # 检查电池
            battery_info = await executor.get_battery_info()
            if battery_info.level < 10:
                result.message = f"电量过低({battery_info.level}%)"
                return result

            # 检查存储
            storage_info = await executor.get_storage_info()
            if storage_info.available < 50 * 1024 * 1024:  # 50MB
                result.message = "存储空间不足"
                return result

            result.success = True
            result.message = "设备状态正常"

        except Exception as e:
            result.message = f"验证异常: {str(e)}"

        return result