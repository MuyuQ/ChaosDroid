"""场景执行编排器和状态机."""
import json
import logging
from abc import ABC, abstractmethod
from datetime import datetime
from enum import Enum
from typing import Callable, Optional, Dict, Any

from sqlalchemy import select

from app.models import RunStatus as ModelRunStatus, ScenarioRun, ScenarioStep
from app.models.base import StepStatus, StepType
from app.models.database import get_session_context

logger = logging.getLogger(__name__)

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
                          started_at: datetime, finished_at: datetime, summary: Dict[str, Any]) -> Optional[int]:
        """记录执行步骤到数据库.

        Args:
            scenario_run: 执行记录
            step_type: 步骤类型
            status: 步骤状态
            started_at: 开始时间
            finished_at: 结束时间
            summary: 步骤摘要

        Returns:
            Optional[int]: 步骤ID
        """
        try:
            async with get_session_context() as session:
                # 获取现有步骤数量
                result = await session.execute(
                    select(ScenarioStep)
                    .where(ScenarioStep.scenario_run_id == scenario_run.id)
                    .order_by(ScenarioStep.step_order.desc())
                    .limit(1)
                )
                last_step = result.scalar_one_or_none()
                next_order = (last_step and last_step.step_order or 0) + 1

                # 创建步骤记录
                step = ScenarioStep(
                    scenario_run_id=scenario_run.id,
                    step_type=step_type,
                    step_order=next_order,
                    status=status,
                    started_at=started_at,
                    finished_at=finished_at,
                    summary_json=json.dumps(summary, ensure_ascii=False),
                )
                session.add(step)
                await session.commit()

                # 获取步骤ID
                await session.refresh(step)
                logger.debug(f"记录步骤: {step_type} -> {status}, step_id={step.id}")
                return step.id

        except Exception as e:
            logger.exception(f"记录步骤失败: {str(e)}")
            return None


class PreparingHandler(BaseStateHandler):
    """准备阶段处理器"""

    @property
    def status(self) -> RunStatus:
        return RunStatus.PREPARING

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
            # 获取设备执行器（从context或创建新的）
            executor = context.get("executor")
            if not executor:
                # 从执行服务获取执行器
                from app.services.execution_service import ExecutionService
                exec_service = context.get("execution_service")
                if exec_service:
                    executor = exec_service._setup_executor(
                        context.get("executor_mode", "mock"),
                        scenario_run.device_serial,
                        context,
                    )
                    context["executor"] = executor

            if not executor:
                logger.error("无法获取执行器")
                await self.record_step(
                    scenario_run, StepType.PRECHECK.value, StepStatus.FAILED.value,
                    started_at, datetime.utcnow(),
                    {"error": "no_executor", "message": "无法获取执行器"}
                )
                return RunStatus.FAILED

            # 检查设备在线
            if not await executor.is_online():
                await self.record_step(
                    scenario_run, StepType.PRECHECK.value, StepStatus.FAILED.value,
                    started_at, datetime.utcnow(),
                    {"error": "device_offline", "message": "设备不在线"}
                )
                return RunStatus.FAILED

            # 采集设备属性
            properties = await executor.get_properties()
            battery_info = await executor.get_battery_info()
            storage_info = await executor.get_storage_info()
            boot_completed = await executor.check_boot_completed()

            # 检查基础条件
            issues = []
            fault_profile = context.get("fault_profile", {})

            # 根据故障类型调整检查条件
            min_battery_level = 20
            min_storage_mb = 100

            if fault_profile.get("fault_type") == "storage_pressure":
                params = fault_profile.get("parameters", {})
                pressure_mb = params.get("pressure_mb", 1000)
                min_storage_mb = pressure_mb + 100

            if fault_profile.get("fault_type") == "low_battery":
                min_battery_level = 0  # 低电量场景不需要电量检查

            if battery_info.level < min_battery_level:
                issues.append({
                    "type": "low_battery",
                    "current": battery_info.level,
                    "required": min_battery_level,
                })

            if storage_info.available < min_storage_mb * 1024 * 1024:
                issues.append({
                    "type": "storage_low",
                    "current_mb": storage_info.available // (1024 * 1024),
                    "required_mb": min_storage_mb,
                })

            if not boot_completed:
                issues.append({
                    "type": "boot_not_completed",
                })

            if issues:
                await self.record_step(
                    scenario_run, StepType.PRECHECK.value, StepStatus.FAILED.value,
                    started_at, datetime.utcnow(),
                    {
                        "error": "precheck_failed",
                        "issues": issues,
                        "properties": properties,
                        "battery": {"level": battery_info.level, "status": battery_info.status},
                        "storage": {
                            "total_mb": storage_info.total // (1024 * 1024),
                            "available_mb": storage_info.available // (1024 * 1024),
                        },
                        "message": f"前置检查失败: {len(issues)}个问题",
                    }
                )
                return RunStatus.FAILED

            from dataclasses import asdict

            step_id = await self.record_step(
                scenario_run, StepType.PRECHECK.value, StepStatus.SUCCESS.value,
                started_at, datetime.utcnow(),
                {
                    "properties": properties,
                    "battery": asdict(battery_info),
                    "storage": asdict(storage_info),
                    "boot_completed": boot_completed,
                    "message": "准备阶段完成",
                }
            )

            # 保存初始观测
            context["initial_state"] = {
                "properties": properties,
                "battery": asdict(battery_info),
                "storage": asdict(storage_info),
                "boot_completed": boot_completed,
            }

            # 获取注入阶段，决定下一步
            inject_stage = scenario_run.inject_stage
            if inject_stage == "precheck":
                return RunStatus.INJECTING
            else:
                return RunStatus.INJECTING

        except Exception as e:
            logger.exception("准备阶段异常")
            await self.record_step(
                scenario_run, StepType.PRECHECK.value, StepStatus.FAILED.value,
                started_at, datetime.utcnow(),
                {"error": str(e), "message": f"准备阶段异常: {str(e)}"}
            )
            return RunStatus.FAILED


class InjectingHandler(BaseStateHandler):
    """注入阶段处理器"""

    @property
    def status(self) -> RunStatus:
        return RunStatus.INJECTING

    async def handle(self, scenario_run: ScenarioRun, context: Dict[str, Any]) -> RunStatus:
        """
        注入阶段职责:
        - 根据 FaultProfile 执行注入动作
        - 记录注入成功或失败
        - 对需要持续存在的故障保持注入状态
        """
        started_at = datetime.utcnow()

        try:
            # 获取注入器（从context或创建新的）
            injector = context.get("injector")
            executor = context.get("executor")

            if not executor:
                logger.error("无法获取执行器")
                await self.record_step(
                    scenario_run, StepType.INJECT.value, StepStatus.FAILED.value,
                    started_at, datetime.utcnow(),
                    {"error": "no_executor", "message": "无法获取执行器"}
                )
                return RunStatus.FAILED

            # 如果没有注入器，跳过注入阶段
            if not injector:
                logger.info("没有注入器，跳过注入阶段")
                await self.record_step(
                    scenario_run, StepType.INJECT.value, StepStatus.SUCCESS.value,
                    started_at, datetime.utcnow(),
                    {"skipped": True, "message": "没有配置注入器，跳过注入"}
                )
                return RunStatus.VALIDATING

            # 构建注入上下文
            from app.injectors.base import InjectContext
            from app.config.settings import get_settings

            settings = get_settings()
            artifacts_dir = settings.get_artifacts_dir() / str(scenario_run.id)

            inject_context = InjectContext(
                scenario_run_id=scenario_run.id,
                device_serial=scenario_run.device_serial,
                executor=executor,
                fault_profile=context.get("fault_profile", {}),
                artifacts_dir=str(artifacts_dir),
                started_at=started_at,
                inject_stage=scenario_run.inject_stage,
            )

            # 准备注入环境
            prepare_result = await injector.prepare(inject_context)
            if not prepare_result:
                await self.record_step(
                    scenario_run, StepType.INJECT.value, StepStatus.FAILED.value,
                    started_at, datetime.utcnow(),
                    {"error": "prepare_failed", "message": "注入准备失败"}
                )
                context["inject_failed"] = True
                return RunStatus.RECOVERING

            # 执行注入
            inject_result = await injector.inject(inject_context)

            # 保存注入结果到context
            context["inject_result"] = {
                "success": inject_result.success,
                "fault_injected": inject_result.fault_injected,
                "fault_observed": inject_result.fault_observed,
                "message": inject_result.message,
                "details": inject_result.details,
                "cleanup_required": inject_result.cleanup_required,
            }
            context["inject_context"] = inject_context

            step_status = StepStatus.SUCCESS.value if inject_result.success else StepStatus.FAILED.value
            await self.record_step(
                scenario_run, StepType.INJECT.value, step_status,
                started_at, datetime.utcnow(),
                {
                    "success": inject_result.success,
                    "fault_injected": inject_result.fault_injected,
                    "fault_observed": inject_result.fault_observed,
                    "message": inject_result.message,
                    "details": inject_result.details,
                    "cleanup_required": inject_result.cleanup_required,
                }
            )

            if inject_result.success:
                logger.info(f"注入成功: {inject_result.message}")
                return RunStatus.VALIDATING
            else:
                # 注入失败，进入恢复阶段尝试清理
                logger.warning(f"注入失败: {inject_result.message}")
                context["inject_failed"] = True
                return RunStatus.RECOVERING

        except Exception as e:
            logger.exception("注入阶段异常")
            await self.record_step(
                scenario_run, StepType.INJECT.value, StepStatus.FAILED.value,
                started_at, datetime.utcnow(),
                {"error": str(e), "message": f"注入阶段异常: {str(e)}"}
            )
            context["inject_failed"] = True
            return RunStatus.RECOVERING


class ValidatingHandler(BaseStateHandler):
    """验证阶段处理器"""

    @property
    def status(self) -> RunStatus:
        return RunStatus.VALIDATING

    async def handle(self, scenario_run: ScenarioRun, context: Dict[str, Any]) -> RunStatus:
        """
        验证阶段职责:
        - 执行 ValidationProfile
        - 判断系统是否表现出预期异常
        - 判断核心功能是否仍然可达
        """
        started_at = datetime.utcnow()

        try:
            # 获取验证器（从context或创建默认验证器）
            validator = context.get("validator")
            executor = context.get("executor")

            if not executor:
                logger.error("无法获取执行器")
                await self.record_step(
                    scenario_run, StepType.VALIDATE.value, StepStatus.FAILED.value,
                    started_at, datetime.utcnow(),
                    {"error": "no_executor", "message": "无法获取执行器"}
                )
                return RunStatus.RECOVERING

            # 如果没有验证器，使用默认验证器
            if not validator:
                from app.validators.base import DefaultValidator
                validator = DefaultValidator()
                context["validator"] = validator

            # 构建验证上下文
            from app.validators.base import ValidationContext
            from app.config.settings import get_settings

            settings = get_settings()
            artifacts_dir = settings.get_artifacts_dir() / str(scenario_run.id)

            validation_context = ValidationContext(
                scenario_run_id=scenario_run.id,
                device_serial=scenario_run.device_serial,
                executor=executor,
                validation_profile=context.get("validation_profile", {}),
                inject_result=context.get("inject_result"),
                artifacts_dir=str(artifacts_dir),
                started_at=started_at,
            )

            # 执行验证
            validation_result = await validator.validate(validation_context)

            # 保存验证结果到context
            context["validation_result"] = {
                "passed": validation_result.passed,
                "fault_observed": validation_result.fault_observed,
                "message": validation_result.message,
                "checks": [
                    {
                        "check_name": c.check_name,
                        "passed": c.passed,
                        "expected": str(c.expected),
                        "actual": str(c.actual),
                        "message": c.message,
                    }
                    for c in validation_result.checks
                ],
            }

            step_status = StepStatus.SUCCESS.value if validation_result.passed else StepStatus.FAILED.value
            await self.record_step(
                scenario_run, StepType.VALIDATE.value, step_status,
                started_at, datetime.utcnow(),
                {
                    "passed": validation_result.passed,
                    "fault_observed": validation_result.fault_observed,
                    "message": validation_result.message,
                    "total_checks": len(validation_result.checks),
                    "passed_checks": sum(1 for c in validation_result.checks if c.passed),
                    "failed_checks": sum(1 for c in validation_result.checks if not c.passed),
                }
            )

            logger.info(f"验证完成: {validation_result.message}")
            return RunStatus.RECOVERING

        except Exception as e:
            logger.exception("验证阶段异常")
            await self.record_step(
                scenario_run, StepType.VALIDATE.value, StepStatus.FAILED.value,
                started_at, datetime.utcnow(),
                {"error": str(e), "message": f"验证阶段异常: {str(e)}"}
            )
            return RunStatus.RECOVERING


class RecoveringHandler(BaseStateHandler):
    """恢复阶段处理器"""

    @property
    def status(self) -> RunStatus:
        return RunStatus.RECOVERING

    async def handle(self, scenario_run: ScenarioRun, context: Dict[str, Any]) -> RunStatus:
        """
        恢复阶段职责:
        - 执行 RecoveryProfile
        - 检查故障是否被移除
        - 检查设备是否恢复可用
        """
        started_at = datetime.utcnow()

        try:
            executor = context.get("executor")
            injector = context.get("injector")
            inject_context = context.get("inject_context")

            if not executor:
                logger.error("无法获取执行器")
                await self.record_step(
                    scenario_run, StepType.RECOVER.value, StepStatus.FAILED.value,
                    started_at, datetime.utcnow(),
                    {"error": "no_executor", "message": "无法获取执行器"}
                )
                return self._determine_final_status(context)

            # 使用恢复服务执行恢复步骤
            from app.services.recovery_service import RecoveryService

            recovery_service = RecoveryService(context.get("recovery_profile"))

            # 如果有inject_context，使用它；否则重新构建
            if not inject_context and injector:
                from app.injectors.base import InjectContext
                from app.config.settings import get_settings
                settings = get_settings()
                artifacts_dir = settings.get_artifacts_dir() / str(scenario_run.id)
                inject_context = InjectContext(
                    scenario_run_id=scenario_run.id,
                    device_serial=scenario_run.device_serial,
                    executor=executor,
                    fault_profile=context.get("fault_profile", {}),
                    artifacts_dir=str(artifacts_dir),
                    inject_stage=scenario_run.inject_stage,
                )
                context["inject_context"] = inject_context

            # 执行恢复
            recovery_result = await recovery_service.execute_recovery_steps(executor, context)

            # 保存恢复结果到context
            context["recovery_result"] = recovery_result
            context["cleanup_result"] = recovery_result.get("cleanup_success", True)

            step_status = StepStatus.SUCCESS.value if recovery_result.get("passed", False) else StepStatus.FAILED.value
            await self.record_step(
                scenario_run, StepType.RECOVER.value, step_status,
                started_at, datetime.utcnow(),
                {
                    "passed": recovery_result.get("passed", False),
                    "cleanup_success": recovery_result.get("cleanup_success", True),
                    "verification_success": recovery_result.get("verification_success", True),
                    "message": recovery_result.get("message", ""),
                    "manual_action_required": recovery_result.get("manual_action_required", False),
                }
            )

            # 计算最终结果
            final_status = self._determine_final_status(context)
            logger.info(f"恢复完成，最终状态: {final_status.value}")
            return final_status

        except Exception as e:
            logger.exception("恢复阶段异常")
            await self.record_step(
                scenario_run, StepType.RECOVER.value, StepStatus.FAILED.value,
                started_at, datetime.utcnow(),
                {"error": str(e), "message": f"恢复阶段异常: {str(e)}"}
            )
            return self._determine_final_status(context)

    def _determine_final_status(self, context: Dict[str, Any]) -> RunStatus:
        """根据各阶段结果确定最终状态.

        根据规范:
        - 注入成功 + 验证通过 + 恢复通过 = passed
        - 注入成功 + 验证失败 + 恢复通过 = failed
        - 注入成功 + 验证通过 + 恢复失败 = partial
        - 注入失败 = failed
        """
        inject_failed = context.get("inject_failed", False)

        if inject_failed:
            return RunStatus.FAILED

        inject_result = context.get("inject_result", {})
        validation_result = context.get("validation_result", {})
        recovery_result = context.get("recovery_result", {})

        fault_injected = inject_result.get("fault_injected", False)
        validation_passed = validation_result.get("passed", True)
        recovery_passed = recovery_result.get("passed", True)

        # 根据规范判定最终状态
        if not fault_injected:
            return RunStatus.FAILED

        if fault_injected and validation_passed and recovery_passed:
            return RunStatus.PASSED

        if fault_injected and not validation_passed and recovery_passed:
            return RunStatus.FAILED

        if fault_injected and validation_passed and not recovery_passed:
            return RunStatus.PARTIAL

        return RunStatus.FAILED


# 注册状态处理器
STATE_HANDLERS[RunStatus.PREPARING] = PreparingHandler()
STATE_HANDLERS[RunStatus.INJECTING] = InjectingHandler()
STATE_HANDLERS[RunStatus.VALIDATING] = ValidatingHandler()
STATE_HANDLERS[RunStatus.RECOVERING] = RecoveringHandler()


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
                logger.error(f"找不到执行记录 run_id={self.scenario_run_id}")
                return RunStatus.FAILED

            # 加载场景模板和相关配置
            await self._load_scenario_config(session, scenario_run)

            # 初始化状态为 preparing
            scenario_run.status = RunStatus.PREPARING.value
            scenario_run.started_at = datetime.utcnow()
            await session.commit()

            # 状态机循环
            current_status = RunStatus.PREPARING
            while current_status in STATE_HANDLERS:
                handler = STATE_HANDLERS[current_status]
                logger.info(f"执行状态处理器: {current_status.value}")

                # 刷新scenario_run以获取最新数据
                await session.refresh(scenario_run)
                scenario_run.status = current_status.value
                await session.commit()

                # 执行状态处理
                next_status = await handler.handle(scenario_run, self.context)

                # 更新状态
                current_status = next_status
                scenario_run.status = next_status.value
                scenario_run.finished_at = datetime.utcnow()
                await session.commit()

                logger.info(f"状态转换: {scenario_run.status}")

            # 生成报告
            await self._generate_report(session, scenario_run)

            return RunStatus(scenario_run.status)

    async def _load_scenario_config(self, session, scenario_run: ScenarioRun) -> None:
        """加载场景配置到context."""
        from app.models import ScenarioTemplate, FaultProfile, ValidationProfile, RecoveryProfile

        # 获取场景模板
        if scenario_run.scenario_template_id:
            template = await session.get(ScenarioTemplate, scenario_run.scenario_template_id)
            if template:
                self.context["scenario_template"] = template
                self.context["executor_mode"] = template.executor_mode

                # 获取故障配置
                if template.fault_profile_id:
                    fault_profile = await session.get(FaultProfile, template.fault_profile_id)
                    if fault_profile:
                        self.context["fault_profile"] = {
                            "id": fault_profile.id,
                            "name": fault_profile.name,
                            "fault_type": fault_profile.fault_type,
                            "parameters": fault_profile.parameters or {},
                            "safe_cleanup_required": fault_profile.safe_cleanup_required,
                            "risk_level": fault_profile.risk_level,
                        }

                        # 设置注入器
                        from app.injectors.base import get_injector
                        injector = get_injector(fault_profile.fault_type)
                        self.context["injector"] = injector

                # 获取验证配置
                if template.validation_profile_id:
                    validation_profile = await session.get(ValidationProfile, template.validation_profile_id)
                    if validation_profile:
                        self.context["validation_profile"] = {
                            "id": validation_profile.id,
                            "name": validation_profile.name,
                            "checks": json.loads(validation_profile.checks_json or "{}"),
                            "timeout_sec": validation_profile.timeout_sec,
                            "pass_rules": json.loads(validation_profile.pass_rules_json or "{}"),
                        }

                # 获取恢复配置
                if template.recovery_profile_id:
                    recovery_profile = await session.get(RecoveryProfile, template.recovery_profile_id)
                    if recovery_profile:
                        self.context["recovery_profile"] = {
                            "id": recovery_profile.id,
                            "name": recovery_profile.name,
                            "steps": json.loads(recovery_profile.steps_json or "{}"),
                            "manual_intervention_allowed": recovery_profile.manual_intervention_allowed,
                            "timeout_sec": recovery_profile.timeout_sec,
                        }

        # 设置基本context信息
        self.context["scenario_run_id"] = scenario_run.id
        self.context["device_serial"] = scenario_run.device_serial
        self.context["inject_stage"] = scenario_run.inject_stage

    async def _generate_report(self, session, scenario_run: ScenarioRun) -> None:
        """生成执行报告."""
        try:
            from app.services.report_generator import ReportGenerator, ReportData
            from app.validators.base import JudgmentResult

            # 计算执行时长
            started_at = scenario_run.started_at
            finished_at = scenario_run.finished_at or datetime.utcnow()
            duration_sec = 0.0
            if started_at:
                duration_sec = (finished_at - started_at).total_seconds()

            # 获取场景名称
            scenario_name = "Unknown"
            if scenario_run.scenario_template_id:
                template = await session.get(ScenarioTemplate, scenario_run.scenario_template_id)
                if template:
                    scenario_name = template.name

            # 构建判定结果
            inject_result = self.context.get("inject_result", {})
            validation_result = self.context.get("validation_result", {})
            recovery_result = self.context.get("recovery_result", {})
            fault_profile = self.context.get("fault_profile", {})

            judgment = JudgmentResult(
                fault_injected=inject_result.get("fault_injected", False),
                fault_observed=validation_result.get("fault_observed", False),
                validation_passed=validation_result.get("passed", True),
                recovery_passed=recovery_result.get("passed", True),
                risk_level=fault_profile.get("risk_level", "medium"),
                manual_action_required=recovery_result.get("manual_action_required", False),
                final_status=scenario_run.status,
                message=f"注入:{inject_result.get('message', 'N/A')}, 验证:{validation_result.get('message', 'N/A')}, 恢复:{recovery_result.get('message', 'N/A')}",
            )

            # 构建报告数据
            report_data = ReportData(
                scenario_name=scenario_name,
                device_serial=scenario_run.device_serial,
                inject_stage=scenario_run.inject_stage,
                fault_type=fault_profile.get("fault_type", ""),
                inject_summary=inject_result,
                validation_summary=validation_result,
                recovery_summary=recovery_result,
                judgment=judgment,
                evidence=self.context.get("observations", {}),
                started_at=started_at,
                finished_at=finished_at,
                duration_sec=duration_sec,
            )

            # 生成报告
            generator = ReportGenerator(self.scenario_run_id)
            paths = generator.save_reports(report_data)
            summary_json = generator.generate_summary_json(report_data)

            # 保存报告记录
            from app.models import Report
            report = Report(
                scenario_run_id=self.scenario_run_id,
                markdown_path=paths["markdown_path"],
                html_path=paths["html_path"],
                summary_json=summary_json,
            )
            session.add(report)

            # 更新执行记录的结果摘要
            scenario_run.result_summary_json = summary_json
            await session.commit()

            logger.info(f"报告已生成: {paths['markdown_path']}")

        except Exception as e:
            logger.exception(f"生成报告失败: {str(e)}")

    async def setup_context(self, executor, injector, validator, recovery):
        """设置执行上下文（手动调用）"""
        self.context["executor"] = executor
        self.context["injector"] = injector
        self.context["validator"] = validator
        self.context["recovery"] = recovery