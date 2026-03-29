"""场景执行编排器和状态机."""
from abc import ABC, abstractmethod
from datetime import datetime
from enum import Enum
from typing import Callable, Optional, Dict, Any

from chaosdroid.models import RunStatus as ModelRunStatus, ScenarioRun
from chaosdroid.models.database import get_session_context


# 使用模型中的RunStatus
RunStatus = ModelRunStatus


# 状态处理器映射
STATE_HANDLERS: Dict[RunStatus, Callable] = {}


class BaseStateHandler(ABC):
    """状态处理器基类"""

    @property
    @abstractmethod
    def status(self) -> RunStatus:
        """当前状态"""
        pass

    @abstractmethod
    async def handle(self, scenario_run: ScenarioRun, context: Dict[str, Any]) -> RunStatus:
        """处理当前状态，返回下一个状态"""
        pass

    async def record_step(self, scenario_run: ScenarioRun, step_type: str, status: str,
                          started_at: datetime, finished_at: datetime, summary: Dict[str, Any]):
        """记录执行步骤"""
        # TODO: 实现步骤记录
        pass


class PreparingHandler(BaseStateHandler):
    """准备阶段处理器"""

    @property
    def status(self) -> RunStatus:
        return RunStatus.preparing

    async def handle(self, scenario_run: ScenarioRun, context: Dict[str, Any]) -> RunStatus:
        """
        准备阶段职责:
        - 检查设备在线
        - 采集设备基础属性
        - 检查电量、boot状态、可用空间
        - 初始化任务目录
        """
        started_at = datetime.utcnow()

        try:
            # 获取设备执行器
            executor = context.get("executor")
            if not executor:
                return RunStatus.failed

            # 检查设备在线
            if not await executor.is_online():
                await self.record_step(
                    scenario_run, "precheck", "failed",
                    started_at, datetime.utcnow(),
                    {"error": "device_offline"}
                )
                return RunStatus.failed

            # 采集设备属性
            properties = await executor.get_properties()
            battery_info = await executor.get_battery_info()
            storage_info = await executor.get_storage_info()

            # 检查基础条件
            issues = []
            if battery_info.level < 20:
                issues.append("low_battery")
            if storage_info.available < 100 * 1024 * 1024:  # 100MB
                issues.append("storage_low")

            if issues:
                await self.record_step(
                    scenario_run, "precheck", "failed",
                    started_at, datetime.utcnow(),
                    {"error": "precheck_failed", "issues": issues}
                )
                return RunStatus.failed

            # 初始化任务目录
            # TODO: 创建artifacts目录

            from dataclasses import asdict

            await self.record_step(
                scenario_run, "precheck", "passed",
                started_at, datetime.utcnow(),
                {"properties": properties, "battery": asdict(battery_info), "storage": asdict(storage_info)}
            )

            # 获取注入阶段，决定下一步
            inject_stage = scenario_run.inject_stage
            if inject_stage == "precheck":
                return RunStatus.injecting
            else:
                return RunStatus.injecting

        except Exception as e:
            await self.record_step(
                scenario_run, "precheck", "failed",
                started_at, datetime.utcnow(),
                {"error": str(e)}
            )
            return RunStatus.failed


class InjectingHandler(BaseStateHandler):
    """注入阶段处理器"""

    @property
    def status(self) -> RunStatus:
        return RunStatus.injecting

    async def handle(self, scenario_run: ScenarioRun, context: Dict[str, Any]) -> RunStatus:
        """
        注入阶段职责:
        - 根据 FaultProfile 执行注入动作
        - 记录注入成功或失败
        - 对需要持续存在的故障保持注入状态
        """
        started_at = datetime.utcnow()

        try:
            # 获取注入器
            injector = context.get("injector")
            if not injector:
                return RunStatus.failed

            # 准备注入环境
            prepare_result = await injector.prepare(context)
            if not prepare_result:
                await self.record_step(
                    scenario_run, "inject", "failed",
                    started_at, datetime.utcnow(),
                    {"error": "prepare_failed"}
                )
                return RunStatus.failed

            # 执行注入
            inject_result = await injector.inject(context)

            await self.record_step(
                scenario_run, "inject", inject_result.success and "passed" or "failed",
                started_at, datetime.utcnow(),
                inject_result.model_dump()
            )

            context["inject_result"] = inject_result

            if inject_result.success:
                return RunStatus.validating
            else:
                # 注入失败，进入恢复阶段尝试清理
                context["inject_failed"] = True
                return RunStatus.recovering

        except Exception as e:
            await self.record_step(
                scenario_run, "inject", "failed",
                started_at, datetime.utcnow(),
                {"error": str(e)}
            )
            return RunStatus.failed


class ValidatingHandler(BaseStateHandler):
    """验证阶段处理器"""

    @property
    def status(self) -> RunStatus:
        return RunStatus.validating

    async def handle(self, scenario_run: ScenarioRun, context: Dict[str, Any]) -> RunStatus:
        """
        验证阶段职责:
        - 执行 ValidationProfile
        - 判断系统是否表现出预期异常
        - 判断核心功能是否仍然可达
        """
        started_at = datetime.utcnow()

        try:
            # 获取验证器
            validator = context.get("validator")
            if not validator:
                # 没有验证器，默认通过
                return RunStatus.recovering

            # 执行验证
            validation_result = await validator.validate(context)

            await self.record_step(
                scenario_run, "validate", validation_result.passed and "passed" or "failed",
                started_at, datetime.utcnow(),
                validation_result.model_dump()
            )

            context["validation_result"] = validation_result

            return RunStatus.recovering

        except Exception as e:
            await self.record_step(
                scenario_run, "validate", "failed",
                started_at, datetime.utcnow(),
                {"error": str(e)}
            )
            return RunStatus.recovering


class RecoveringHandler(BaseStateHandler):
    """恢复阶段处理器"""

    @property
    def status(self) -> RunStatus:
        return RunStatus.recovering

    async def handle(self, scenario_run: ScenarioRun, context: Dict[str, Any]) -> RunStatus:
        """
        恢复阶段职责:
        - 执行 RecoveryProfile
        - 检查故障是否被移除
        - 检查设备是否恢复可用
        """
        started_at = datetime.utcnow()

        try:
            # 获取恢复策略
            recovery = context.get("recovery")
            injector = context.get("injector")

            # 清理注入
            if injector:
                cleanup_result = await injector.cleanup(context)
                context["cleanup_result"] = cleanup_result

            # 执行恢复步骤
            recovery_result = None
            if recovery:
                recovery_result = await recovery.execute(context)

            await self.record_step(
                scenario_run, "recover", "passed" if (context.get("cleanup_result") or True) else "failed",
                started_at, datetime.utcnow(),
                {"cleanup": context.get("cleanup_result"), "recovery": recovery_result}
            )

            context["recovery_result"] = recovery_result

            # 计算最终结果
            inject_result = context.get("inject_result")
            validation_result = context.get("validation_result")
            inject_failed = context.get("inject_failed", False)

            if inject_failed:
                # 注入失败
                return RunStatus.failed

            inject_success = inject_result and inject_result.success
            validation_passed = validation_result and validation_result.passed
            recovery_passed = context.get("cleanup_result", True) and (recovery_result and recovery_result.passed or True)

            if inject_success and validation_passed and recovery_passed:
                return RunStatus.passed
            elif inject_success and not validation_passed and recovery_passed:
                return RunStatus.failed
            elif inject_success and validation_passed and not recovery_passed:
                return RunStatus.partial
            else:
                return RunStatus.failed

        except Exception as e:
            await self.record_step(
                scenario_run, "recover", "failed",
                started_at, datetime.utcnow(),
                {"error": str(e)}
            )
            return RunStatus.partial


# 注册状态处理器
STATE_HANDLERS[RunStatus.preparing] = PreparingHandler()
STATE_HANDLERS[RunStatus.injecting] = InjectingHandler()
STATE_HANDLERS[RunStatus.validating] = ValidatingHandler()
STATE_HANDLERS[RunStatus.recovering] = RecoveringHandler()


class ScenarioOrchestrator:
    """场景编排器 - 执行状态机"""

    def __init__(self, scenario_run_id: int):
        self.scenario_run_id = scenario_run_id
        self.context: Dict[str, Any] = {}

    async def run(self) -> RunStatus:
        """
        执行场景状态机

        流程: queued -> preparing -> injecting -> validating -> recovering -> passed/failed/partial
        """
        async with get_session_context() as session:
            # 获取执行记录
            scenario_run = await session.get(ScenarioRun, self.scenario_run_id)
            if not scenario_run:
                return RunStatus.failed

            # 初始化状态为 preparing
            scenario_run.status = RunStatus.preparing
            scenario_run.started_at = datetime.utcnow()
            await session.commit()

            # 状态机循环
            while scenario_run.status in STATE_HANDLERS:
                handler = STATE_HANDLERS[scenario_run.status]
                next_status = await handler.handle(scenario_run, self.context)

                # 更新状态
                scenario_run.status = next_status
                scenario_run.finished_at = datetime.utcnow()
                await session.commit()

            return scenario_run.status

    async def setup_context(self, executor, injector, validator, recovery):
        """设置执行上下文"""
        self.context["executor"] = executor
        self.context["injector"] = injector
        self.context["validator"] = validator
        self.context["recovery"] = recovery