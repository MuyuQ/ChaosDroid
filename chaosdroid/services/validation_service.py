"""验证服务模块.

负责验证逻辑的执行，包括验证器设置和验证步骤调用。
"""
import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, Optional

from chaosdroid.validators.base import (
    BaseValidator,
    DefaultValidator,
    ValidationContext,
    ValidationResult,
)
from chaosdroid.models import StepStatus, StepType
from chaosdroid.models.database import get_session_context
from chaosdroid.models.scenario import ScenarioStep

logger = logging.getLogger(__name__)


class ValidationService:
    """验证服务.

    负责：
    - 设置验证器
    - 执行验证操作
    - 处理验证超时和异常
    - 记录验证步骤
    """

    def __init__(self, validate_timeout: int = 180):
        """初始化验证服务.

        Args:
            validate_timeout: 验证阶段超时（秒）
        """
        self._validate_timeout = validate_timeout

    async def setup_validator(
        self,
        validation_profile: Optional[Dict[str, Any]],
        context: Dict[str, Any],
    ) -> BaseValidator:
        """设置验证器.

        Args:
            validation_profile: 验证配置
            context: 执行上下文

        Returns:
            验证器实例
        """
        checks_config = validation_profile and validation_profile.get("checks", {}) or {}
        validator = DefaultValidator(checks_config)
        logger.info("设置默认验证器")
        return validator

    async def execute_validation(
        self,
        scenario_run_id: int,
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """执行验证操作.

        Args:
            scenario_run_id: 场景执行记录 ID
            context: 执行上下文

        Returns:
            验证结果
        """
        validator = context.get("validator")
        executor = context["executor"]
        validation_profile = context.get("validation_profile", {})
        artifacts_dir = context["artifacts_dir"]
        inject_result = context.get("inject_result")

        started_at = datetime.utcnow()
        timeout_sec = self._validate_timeout

        result = {
            "passed": False,
            "started_at": started_at.isoformat(),
            "finished_at": None,
            "checks": [],
            "details": {},
            "timeout_sec": timeout_sec,
        }

        if validator is None:
            result["passed"] = True
            result["skipped"] = True
            result["message"] = "没有配置验证器，跳过验证"
            return result

        try:
            async with asyncio.timeout(timeout_sec):
                validation_context = ValidationContext(
                    scenario_run_id=scenario_run_id,
                    device_serial=context["device_serial"],
                    executor=executor,
                    validation_profile=validation_profile,
                    inject_result=inject_result,
                    artifacts_dir=artifacts_dir,
                    started_at=started_at,
                )

                validation_result: ValidationResult = await validator.validate(validation_context)

                result["passed"] = validation_result.passed
                result["fault_observed"] = validation_result.fault_observed
                result["checks"] = [
                    {
                        "check_name": c.check_name,
                        "passed": c.passed,
                        "expected": c.expected,
                        "actual": c.actual,
                        "message": c.message,
                    }
                    for c in validation_result.checks
                ]
                result["details"] = validation_result.details
                result["message"] = validation_result.message
                result["finished_at"] = datetime.utcnow().isoformat()

            step_status = StepStatus.SUCCESS if result["passed"] else StepStatus.FAILED
            await self._record_step(
                scenario_run_id, StepType.VALIDATE, step_status, result
            )

            logger.info(f"验证完成：{result['message']}")

        except asyncio.TimeoutError:
            result["passed"] = False
            result["error"] = "timeout"
            result["timeout"] = True
            result["message"] = f"验证阶段超时（{timeout_sec}秒）"
            logger.error(f"验证阶段超时：run_id={scenario_run_id}, timeout={timeout_sec}s")
            await self._record_step(
                scenario_run_id, StepType.VALIDATE, StepStatus.TIMEOUT, result
            )

        except Exception as e:
            result["passed"] = False
            result["error"] = str(e)
            result["message"] = f"验证阶段异常：{str(e)}"
            logger.exception("验证阶段异常")
            await self._record_step(
                scenario_run_id, StepType.VALIDATE, StepStatus.FAILED, result
            )

        return result

    async def _record_step(
        self,
        scenario_run_id: int,
        step_type: StepType,
        step_status: StepStatus,
        summary: Dict[str, Any],
    ) -> None:
        """记录验证步骤到数据库."""
        import json
        from sqlalchemy import select

        async with get_session_context() as session:
            result = await session.execute(
                select(ScenarioStep)
                .where(ScenarioStep.scenario_run_id == scenario_run_id)
                .order_by(ScenarioStep.step_order.desc())
                .limit(1)
            )
            last_step = result.scalar_one_or_none()
            next_order = (last_step and last_step.step_order or 0) + 1

            step = ScenarioStep(
                scenario_run_id=scenario_run_id,
                step_type=step_type.value,
                step_order=next_order,
                status=step_status.value,
                started_at=datetime.utcnow(),
                finished_at=datetime.utcnow(),
                summary_json=json.dumps(summary, ensure_ascii=False),
            )
            session.add(step)
            await session.commit()

            logger.debug(f"记录验证步骤：{step_type.value} -> {step_status.value}")


# 全局验证服务实例
_validation_service: Optional[ValidationService] = None


def get_validation_service() -> ValidationService:
    """获取验证服务实例."""
    global _validation_service
    if _validation_service is None:
        _validation_service = ValidationService()
    return _validation_service
