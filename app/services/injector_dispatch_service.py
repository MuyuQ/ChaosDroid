"""注入器分发服务模块.

负责注入器的选择、设置和执行调用。
"""
import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, Optional

from app.injectors.base import BaseInjector, get_injector, InjectContext, InjectResult
from app.models import StepStatus, StepType
from app.models.database import get_session_context
from app.models.scenario import ScenarioStep

logger = logging.getLogger(__name__)


class InjectorDispatchService:
    """注入器分发服务.

    负责：
    - 根据 fault_type 选择和设置注入器
    - 执行注入操作
    - 处理注入超时和异常
    - 记录注入步骤
    """

    def __init__(self, inject_timeout: int = 180):
        """初始化注入器分发服务.

        Args:
            inject_timeout: 注入阶段超时（秒）
        """
        self._inject_timeout = inject_timeout

    async def setup_injector(
        self,
        fault_profile: Optional[Dict[str, Any]],
        context: Dict[str, Any],
    ) -> Optional[BaseInjector]:
        """设置注入器.

        Args:
            fault_profile: 故障配置
            context: 执行上下文

        Returns:
            注入器实例，如果没有找到则返回 None
        """
        if fault_profile is None:
            logger.warning("没有故障配置，跳过注入")
            return None

        fault_type = fault_profile.get("fault_type")
        injector = get_injector(fault_type)

        if injector is None:
            logger.warning(f"找不到注入器 fault_type={fault_type}")
        else:
            logger.info(f"设置注入器 fault_type={fault_type}")

        return injector

    async def execute_inject(
        self,
        scenario_run_id: int,
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """执行注入操作.

        Args:
            scenario_run_id: 场景执行记录 ID
            context: 执行上下文

        Returns:
            注入结果
        """
        injector = context.get("injector")
        executor = context["executor"]
        fault_profile = context.get("fault_profile", {})
        artifacts_dir = context["artifacts_dir"]

        started_at = datetime.utcnow()
        timeout_sec = self._inject_timeout

        result = {
            "success": False,
            "fault_injected": False,
            "fault_observed": False,
            "started_at": started_at.isoformat(),
            "finished_at": None,
            "details": {},
            "timeout_sec": timeout_sec,
        }

        if injector is None:
            result["success"] = True
            result["skipped"] = True
            result["message"] = "没有配置注入器，跳过注入"
            return result

        try:
            async with asyncio.timeout(timeout_sec):
                inject_context = InjectContext(
                    scenario_run_id=scenario_run_id,
                    device_serial=context["device_serial"],
                    executor=executor,
                    fault_profile=fault_profile,
                    artifacts_dir=artifacts_dir,
                    started_at=started_at,
                    inject_stage=context["inject_stage"],
                )

                prepare_success = await injector.prepare(inject_context)
                if not prepare_success:
                    result["success"] = False
                    result["message"] = "注入准备失败"
                    await self._record_step(
                        scenario_run_id, StepType.INJECT, StepStatus.FAILED, result
                    )
                    return result

                inject_result: InjectResult = await injector.inject(inject_context)

                result["success"] = inject_result.success
                result["fault_injected"] = inject_result.fault_injected
                result["fault_observed"] = inject_result.fault_observed
                result["message"] = inject_result.message
                result["details"] = inject_result.details
                result["cleanup_required"] = inject_result.cleanup_required
                result["finished_at"] = datetime.utcnow().isoformat()

            step_status = StepStatus.SUCCESS if result["success"] else StepStatus.FAILED
            await self._record_step(
                scenario_run_id, StepType.INJECT, step_status, result
            )

            logger.info(f"注入完成：{result['message']}")

        except asyncio.TimeoutError:
            result["success"] = False
            result["error"] = "timeout"
            result["timeout"] = True
            result["message"] = f"注入阶段超时（{timeout_sec}秒）"
            result["cleanup_required"] = True
            logger.error(f"注入阶段超时：run_id={scenario_run_id}, timeout={timeout_sec}s")
            await self._record_step(
                scenario_run_id, StepType.INJECT, StepStatus.TIMEOUT, result
            )

        except Exception as e:
            result["success"] = False
            result["error"] = str(e)
            result["message"] = f"注入阶段异常：{str(e)}"
            result["cleanup_required"] = True
            logger.exception("注入阶段异常")
            await self._record_step(
                scenario_run_id, StepType.INJECT, StepStatus.FAILED, result
            )

        return result

    async def _record_step(
        self,
        scenario_run_id: int,
        step_type: StepType,
        step_status: StepStatus,
        summary: Dict[str, Any],
    ) -> None:
        """记录注入步骤到数据库."""
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

            logger.debug(f"记录注入步骤：{step_type.value} -> {step_status.value}")


# 全局注入器分发服务实例
_injector_dispatch_service: Optional[InjectorDispatchService] = None


def get_injector_dispatch_service() -> InjectorDispatchService:
    """获取注入器分发服务实例."""
    global _injector_dispatch_service
    if _injector_dispatch_service is None:
        _injector_dispatch_service = InjectorDispatchService()
    return _injector_dispatch_service
