"""恢复服务模块.

提供故障注入后的恢复操作实现，包括清理注入和设备恢复验证。
"""
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from chaosdroid.config.settings import get_settings
from chaosdroid.executors.base import BaseDeviceExecutor
from chaosdroid.injectors.base import BaseInjector, InjectContext
from chaosdroid.models.base import StepStatus, StepType
from chaosdroid.models.database import get_session_context
from chaosdroid.models.scenario import ScenarioStep
from chaosdroid.observers.collector import ArtifactCollector

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
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "step_name": self.step_name,
            "success": self.success,
            "message": self.message,
            "details": self.details,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
        }


@dataclass
class RecoveryResult:
    """恢复操作结果"""
    passed: bool
    steps: List[RecoveryStepResult] = field(default_factory=list)
    message: str = ""
    manual_action_required: bool = False
    cleanup_success: bool = True
    verification_success: bool = True
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "passed": self.passed,
            "message": self.message,
            "manual_action_required": self.manual_action_required,
            "cleanup_success": self.cleanup_success,
            "verification_success": self.verification_success,
            "steps": [s.to_dict() for s in self.steps],
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
        }


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
    ) -> Dict[str, Any]:
        """执行恢复步骤.

        Args:
            executor: 设备执行器
            context: 执行上下文

        Returns:
            Dict[str, Any]: 恢复操作结果（字典格式）
        """
        started_at = datetime.utcnow()
        scenario_run_id = context.get("scenario_run_id", 0)

        logger.info(f"开始执行恢复步骤，共{len(self.steps)}步 run_id={scenario_run_id}")

        result = RecoveryResult(passed=True, started_at=started_at)
        injector = context.get("injector")

        try:
            # 1. 首先执行注入器清理
            cleanup_result = await self.cleanup_injection(executor, context)
            result.steps.append(cleanup_result)
            result.cleanup_success = cleanup_result.success
            logger.info(f"注入器清理: {'成功' if cleanup_result.success else '失败'}")

            # 2. 执行配置的恢复步骤
            for step in self.steps:
                step_result = await self._execute_single_step(executor, step, context)
                result.steps.append(step_result)

                if not step_result.success and step.required:
                    logger.warning(f"恢复步骤 {step.name} 失败")

            # 3. 最终验证
            verification_result = await self.verify_recovery(executor)
            result.steps.append(verification_result)
            result.verification_success = verification_result.success

            # 判断整体结果
            failed_required_steps = [
                s for s in result.steps
                if not s.success
            ]

            result.passed = result.cleanup_success and result.verification_success
            result.message = result.passed and "恢复成功" or "恢复部分失败"
            result.finished_at = datetime.utcnow()

            # 判断是否需要人工介入
            if not result.passed:
                result.manual_action_required = self.recovery_profile.get(
                    "manual_intervention_allowed", True
                )

            # 记录步骤到数据库
            await self._record_recovery_step(scenario_run_id, result)

        except Exception as e:
            result.passed = False
            result.message = f"恢复过程异常: {str(e)}"
            result.manual_action_required = True
            result.finished_at = datetime.utcnow()
            logger.exception("恢复过程异常")

        logger.info(f"恢复完成: {result.message}")
        return result.to_dict()

    async def cleanup_injection(
        self,
        executor: BaseDeviceExecutor,
        context: Dict[str, Any],
    ) -> RecoveryStepResult:
        """清理注入效果.

        调用注入器的cleanup方法清理注入产生的效果。

        Args:
            executor: 设备执行器
            context: 执行上下文

        Returns:
            RecoveryStepResult: 清理结果
        """
        started_at = datetime.utcnow()
        injector = context.get("injector")
        inject_result = context.get("inject_result", {})
        cleanup_required = inject_result.get("cleanup_required", True)

        logger.info("开始清理注入")

        result = RecoveryStepResult(
            step_name="cleanup_injection",
            success=True,
            started_at=started_at,
            finished_at=datetime.utcnow(),
        )

        # 如果不需要清理，直接返回成功
        if not cleanup_required:
            result.message = "无需清理"
            return result

        # 如果没有注入器，直接返回成功
        if injector is None:
            result.message = "没有注入器，跳过清理"
            return result

        try:
            # 构建注入上下文用于清理
            inject_context = InjectContext(
                scenario_run_id=context.get("scenario_run_id", 0),
                device_serial=context.get("device_serial", ""),
                executor=executor,
                fault_profile=context.get("fault_profile", {}),
                artifacts_dir=context.get("artifacts_dir", ""),
                inject_stage=context.get("inject_stage", "precheck"),
            )

            # 执行清理
            cleanup_success = await injector.cleanup(inject_context)
            result.success = cleanup_success
            result.message = cleanup_success and "清理成功" or "清理失败"
            result.finished_at = datetime.utcnow()

        except Exception as e:
            logger.exception("清理注入异常")
            result.success = False
            result.message = f"清理异常: {str(e)}"
            result.details["error"] = str(e)
            result.finished_at = datetime.utcnow()

        return result

    async def verify_recovery(
        self,
        executor: BaseDeviceExecutor,
    ) -> RecoveryStepResult:
        """验证恢复结果.

        检查设备是否恢复正常状态。

        Args:
            executor: 设备执行器

        Returns:
            RecoveryStepResult: 验证结果
        """
        started_at = datetime.utcnow()
        logger.info("开始验证恢复")

        result = RecoveryStepResult(
            step_name="verify_recovery",
            success=False,
            started_at=started_at,
        )

        try:
            # 检查设备在线
            online = await executor.is_online()
            if not online:
                result.message = "设备离线"
                result.details["online"] = False
                result.details["reason"] = "device_offline"
                result.finished_at = datetime.utcnow()
                return result

            # 检查boot完成
            boot_completed = await executor.check_boot_completed()
            if not boot_completed:
                result.message = "设备启动未完成"
                result.details["online"] = True
                result.details["boot_completed"] = False
                result.details["reason"] = "boot_not_completed"
                result.finished_at = datetime.utcnow()
                return result

            # 检查存储空间
            storage_info = await executor.get_storage_info()
            available_mb = storage_info.available // (1024 * 1024)

            # 检查电量
            battery_info = await executor.get_battery_info()
            battery_level = battery_info.level

            # 判断恢复是否成功
            recovery_ok = (
                online
                and boot_completed
                and available_mb > 50  # 至少50MB可用空间
            )

            result.success = recovery_ok
            result.message = recovery_ok and "恢复验证通过" or "恢复验证失败"
            result.details = {
                "online": online,
                "boot_completed": boot_completed,
                "storage_available_mb": available_mb,
                "battery_level": battery_level,
            }
            result.finished_at = datetime.utcnow()

        except Exception as e:
            logger.exception("恢复验证异常")
            result.success = False
            result.message = f"验证异常: {str(e)}"
            result.details["error"] = str(e)
            result.finished_at = datetime.utcnow()

        return result

    async def _record_recovery_step(
        self,
        scenario_run_id: int,
        result: RecoveryResult,
    ) -> None:
        """记录恢复步骤到数据库."""
        try:
            async with get_session_context() as session:
                from sqlalchemy import select

                db_result = await session.execute(
                    select(ScenarioStep)
                    .where(ScenarioStep.scenario_run_id == scenario_run_id)
                    .order_by(ScenarioStep.step_order.desc())
                    .limit(1)
                )
                last_step = db_result.scalar_one_or_none()
                next_order = (last_step and last_step.step_order or 0) + 1

                # 创建步骤记录
                step_status = StepStatus.SUCCESS if result.passed else StepStatus.FAILED
                step = ScenarioStep(
                    scenario_run_id=scenario_run_id,
                    step_type=StepType.RECOVER.value,
                    step_order=next_order,
                    status=step_status.value,
                    started_at=result.started_at,
                    finished_at=result.finished_at,
                    summary_json=json.dumps(result.to_dict(), ensure_ascii=False),
                )
                session.add(step)
                await session.commit()

                logger.debug(f"记录恢复步骤: {result.passed and '成功' or '失败'}")

        except Exception as e:
            logger.exception(f"记录恢复步骤失败: {str(e)}")

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
        started_at = datetime.utcnow()
        logger.info(f"执行恢复步骤: {step.name} ({step.action})")

        result = RecoveryStepResult(
            step_name=step.name,
            success=False,
            started_at=started_at,
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
        result.finished_at = datetime.utcnow()

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
        此方法为内部调用，使用verify_recovery作为公共接口。
        """
        return await self.verify_recovery(executor)