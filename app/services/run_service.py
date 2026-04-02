"""
场景执行服务模块。

提供 ScenarioRun 和 ScenarioStep 的 CRUD 操作及执行管理。
"""

import json
from datetime import datetime
from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import (
    ExecutorMode,
    InjectStage,
    RunStatus,
    ScenarioRun,
    ScenarioStep,
    ScenarioTemplate,
    StepStatus,
    StepType,
    get_session_context,
)


class RunFilters:
    """执行记录筛选条件。"""

    def __init__(
        self,
        scenario_template_id: int | None = None,
        device_serial: str | None = None,
        status: str | None = None,
        inject_stage: str | None = None,
        started_after: datetime | None = None,
        started_before: datetime | None = None,
    ):
        self.scenario_template_id = scenario_template_id
        self.device_serial = device_serial
        self.status = status
        self.inject_stage = inject_stage
        self.started_after = started_after
        self.started_before = started_before


async def create_run(
    scenario_template_id: int | None,
    device_serial: str,
    executor_mode: str = ExecutorMode.MOCK.value,
    inject_stage: str | None = None,
    session: AsyncSession | None = None,
) -> ScenarioRun:
    """
    创建执行记录。

    Args:
        scenario_template_id: 关联的场景模板ID
        device_serial: 设备序列号
        executor_mode: 执行器模式
        inject_stage: 注入阶段（可选，不传则使用场景模板的配置）
        session: 数据库会话（可选）

    Returns:
        创建的执行记录实例
    """
    async def _create(sess: AsyncSession) -> ScenarioRun:
        # 确定注入阶段
        stage = inject_stage
        if stage is None and scenario_template_id:
            result = await sess.execute(
                select(ScenarioTemplate.inject_stage).where(
                    ScenarioTemplate.id == scenario_template_id
                )
            )
            template = result.scalar_one_or_none()
            if template:
                stage = template

        # 创建执行记录
        run = ScenarioRun(
            scenario_template_id=scenario_template_id,
            device_serial=device_serial,
            status=RunStatus.QUEUED.value,
            inject_stage=stage or InjectStage.PRECHECK.value,
        )

        sess.add(run)
        await sess.flush()
        await sess.refresh(run)
        return run

    if session:
        return await _create(session)

    async with get_session_context() as ctx_session:
        return await _create(ctx_session)


async def get_run(
    run_id: int,
    session: AsyncSession | None = None,
) -> ScenarioRun | None:
    """
    根据ID获取执行记录。

    Args:
        run_id: 执行记录ID
        session: 数据库会话（可选）

    Returns:
        执行记录实例，不存在则返回None
    """
    if session:
        result = await session.execute(
            select(ScenarioRun).where(ScenarioRun.id == run_id)
        )
        return result.scalar_one_or_none()

    async with get_session_context() as ctx_session:
        result = await ctx_session.execute(
            select(ScenarioRun).where(ScenarioRun.id == run_id)
        )
        return result.scalar_one_or_none()


async def get_run_with_template(
    run_id: int,
    session: AsyncSession | None = None,
) -> dict | None:
    """
    获取执行记录及其关联的场景模板。

    Args:
        run_id: 执行记录ID
        session: 数据库会话（可选）

    Returns:
        包含执行记录和场景模板的字典
    """
    async def _get(sess: AsyncSession) -> dict | None:
        result = await sess.execute(
            select(ScenarioRun)
            .options(selectinload(ScenarioRun.scenario_template))
            .where(ScenarioRun.id == run_id)
        )
        run = result.scalar_one_or_none()

        if not run:
            return None

        return {
            "run": run,
            "template": run.scenario_template,
        }

    if session:
        return await _get(session)

    async with get_session_context() as ctx_session:
        return await _get(ctx_session)


async def list_runs(
    filters: RunFilters | None = None,
    offset: int = 0,
    limit: int = 100,
    session: AsyncSession | None = None,
) -> tuple[list[ScenarioRun], int]:
    """
    获取执行记录列表。

    Args:
        filters: 筛选条件
        offset: 偏移量
        limit: 返回数量限制
        session: 数据库会话（可选）

    Returns:
        元组：(执行记录列表, 总数)
    """
    async def _execute_query(sess: AsyncSession) -> tuple[list[ScenarioRun], int]:
        # 构建基础查询
        query = select(ScenarioRun)
        count_query = select(func.count(ScenarioRun.id))

        # 应用筛选条件
        if filters:
            conditions = []

            if filters.scenario_template_id:
                conditions.append(
                    ScenarioRun.scenario_template_id == filters.scenario_template_id
                )

            if filters.device_serial:
                conditions.append(
                    ScenarioRun.device_serial.ilike(f"%{filters.device_serial}%")
                )

            if filters.status:
                conditions.append(ScenarioRun.status == filters.status)

            if filters.inject_stage:
                conditions.append(ScenarioRun.inject_stage == filters.inject_stage)

            if filters.started_after:
                conditions.append(ScenarioRun.started_at >= filters.started_after)

            if filters.started_before:
                conditions.append(ScenarioRun.started_at <= filters.started_before)

            if conditions:
                query = query.where(and_(*conditions))
                count_query = count_query.where(and_(*conditions))

        # 排序：按创建时间倒序
        query = query.order_by(ScenarioRun.created_at.desc())

        # 分页
        query = query.offset(offset).limit(limit)

        # 执行查询
        result = await sess.execute(query)
        runs = list(result.scalars().all())

        # 获取总数
        count_result = await sess.execute(count_query)
        total = count_result.scalar() or 0

        return runs, total

    if session:
        return await _execute_query(session)

    async with get_session_context() as ctx_session:
        return await _execute_query(ctx_session)


async def get_run_steps(
    run_id: int,
    session: AsyncSession | None = None,
) -> list[ScenarioStep]:
    """
    获取执行记录的所有步骤。

    Args:
        run_id: 执行记录ID
        session: 数据库会话（可选）

    Returns:
        步骤列表，按步骤顺序排序
    """
    if session:
        result = await session.execute(
            select(ScenarioStep)
            .where(ScenarioStep.scenario_run_id == run_id)
            .order_by(ScenarioStep.step_order)
        )
        return list(result.scalars().all())

    async with get_session_context() as ctx_session:
        result = await ctx_session.execute(
            select(ScenarioStep)
            .where(ScenarioStep.scenario_run_id == run_id)
            .order_by(ScenarioStep.step_order)
        )
        return list(result.scalars().all())


async def update_run_status(
    run_id: int,
    status: str,
    session: AsyncSession | None = None,
) -> ScenarioRun | None:
    """
    更新执行记录状态。

    Args:
        run_id: 执行记录ID
        status: 新状态
        session: 数据库会话（可选）

    Returns:
        更新后的执行记录实例，不存在则返回None
    """
    async def _update(sess: AsyncSession) -> ScenarioRun | None:
        result = await sess.execute(
            select(ScenarioRun).where(ScenarioRun.id == run_id)
        )
        run = result.scalar_one_or_none()

        if not run:
            return None

        run.status = status

        # 如果是开始状态，设置开始时间
        if status in (RunStatus.PREPARING.value, RunStatus.INJECTING.value):
            if not run.started_at:
                run.started_at = datetime.utcnow()

        # 如果是结束状态，设置结束时间
        if status in (RunStatus.PASSED.value, RunStatus.FAILED.value, RunStatus.PARTIAL.value):
            if not run.finished_at:
                run.finished_at = datetime.utcnow()

        await sess.flush()
        await sess.refresh(run)
        return run

    if session:
        return await _update(session)

    async with get_session_context() as ctx_session:
        return await _update(ctx_session)


async def cancel_run(
    run_id: int,
    session: AsyncSession | None = None,
) -> ScenarioRun | None:
    """
    取消执行记录。

    只有在 queued 或 preparing 状态下才能取消。

    Args:
        run_id: 执行记录ID
        session: 数据库会话（可选）

    Returns:
        更新后的执行记录实例，不存在或无法取消则返回None
    """
    async def _cancel(sess: AsyncSession) -> ScenarioRun | None:
        result = await sess.execute(
            select(ScenarioRun).where(ScenarioRun.id == run_id)
        )
        run = result.scalar_one_or_none()

        if not run:
            return None

        # 只有排队或准备中状态才能取消
        if run.status not in (RunStatus.QUEUED.value, RunStatus.PREPARING.value):
            return None

        run.status = RunStatus.FAILED.value
        run.finished_at = datetime.utcnow()

        # 更新结果摘要
        summary = json.loads(run.result_summary_json or "{}")
        summary["cancelled"] = True
        summary["cancel_reason"] = "用户取消"
        run.result_summary_json = json.dumps(summary, ensure_ascii=False)

        await sess.flush()
        await sess.refresh(run)
        return run

    if session:
        return await _cancel(session)

    async with get_session_context() as ctx_session:
        return await _cancel(ctx_session)


async def create_step(
    run_id: int,
    step_type: str,
    step_order: int,
    session: AsyncSession | None = None,
) -> ScenarioStep:
    """
    创建执行步骤。

    Args:
        run_id: 执行记录ID
        step_type: 步骤类型
        step_order: 步骤顺序
        session: 数据库会话（可选）

    Returns:
        创建的步骤实例
    """
    step = ScenarioStep(
        scenario_run_id=run_id,
        step_type=step_type,
        step_order=step_order,
        status=StepStatus.PENDING.value,
    )

    if session:
        session.add(step)
        await session.flush()
        await session.refresh(step)
        return step

    async with get_session_context() as ctx_session:
        ctx_session.add(step)
        await ctx_session.flush()
        await ctx_session.refresh(step)
        return step


async def record_step_result(
    run_id: int,
    step_type: str,
    status: str,
    summary: dict[str, Any] | None = None,
    step_order: int | None = None,
    session: AsyncSession | None = None,
) -> ScenarioStep | None:
    """
    记录步骤结果。

    如果步骤不存在，会自动创建。如果存在，则更新状态和摘要。

    Args:
        run_id: 执行记录ID
        step_type: 步骤类型
        status: 步骤状态
        summary: 步骤摘要
        step_order: 步骤顺序（创建新步骤时需要）
        session: 数据库会话（可选）

    Returns:
        步骤实例，执行记录不存在则返回None
    """
    async def _record(sess: AsyncSession) -> ScenarioStep | None:
        # 检查执行记录是否存在
        run_result = await sess.execute(
            select(ScenarioRun).where(ScenarioRun.id == run_id)
        )
        run = run_result.scalar_one_or_none()

        if not run:
            return None

        # 查找现有步骤
        step_result = await sess.execute(
            select(ScenarioStep).where(
                and_(
                    ScenarioStep.scenario_run_id == run_id,
                    ScenarioStep.step_type == step_type,
                )
            )
        )
        step = step_result.scalar_one_or_none()

        now = datetime.utcnow()

        if step:
            # 更新现有步骤
            step.status = status
            if summary:
                step.summary_json = json.dumps(summary, ensure_ascii=False)

            # 设置时间
            if status == StepStatus.RUNNING.value:
                step.started_at = now
            elif status in (StepStatus.SUCCESS.value, StepStatus.FAILED.value, StepStatus.TIMEOUT.value):
                step.finished_at = now
        else:
            # 创建新步骤
            if step_order is None:
                # 获取下一个顺序号
                max_order_result = await sess.execute(
                    select(func.max(ScenarioStep.step_order)).where(
                        ScenarioStep.scenario_run_id == run_id
                    )
                )
                max_order = max_order_result.scalar() or 0
                step_order = max_order + 1

            step = ScenarioStep(
                scenario_run_id=run_id,
                step_type=step_type,
                step_order=step_order,
                status=status,
                started_at=now if status == StepStatus.RUNNING.value else None,
                finished_at=now if status in (StepStatus.SUCCESS.value, StepStatus.FAILED.value, StepStatus.TIMEOUT.value) else None,
                summary_json=json.dumps(summary, ensure_ascii=False) if summary else None,
            )
            sess.add(step)

        await sess.flush()
        await sess.refresh(step)
        return step

    if session:
        return await _record(session)

    async with get_session_context() as ctx_session:
        return await _record(ctx_session)


async def update_run_summary(
    run_id: int,
    summary: dict[str, Any],
    session: AsyncSession | None = None,
) -> ScenarioRun | None:
    """
    更新执行记录的结果摘要。

    Args:
        run_id: 执行记录ID
        summary: 结果摘要
        session: 数据库会话（可选）

    Returns:
        更新后的执行记录实例，不存在则返回None
    """
    async def _update(sess: AsyncSession) -> ScenarioRun | None:
        result = await sess.execute(
            select(ScenarioRun).where(ScenarioRun.id == run_id)
        )
        run = result.scalar_one_or_none()

        if not run:
            return None

        run.result_summary_json = json.dumps(summary, ensure_ascii=False)

        await sess.flush()
        await sess.refresh(run)
        return run

    if session:
        return await _update(session)

    async with get_session_context() as ctx_session:
        return await _update(ctx_session)


async def get_run_statistics(
    session: AsyncSession | None = None,
) -> dict[str, Any]:
    """
    获取执行记录统计信息。

    Args:
        session: 数据库会话（可选）

    Returns:
        统计信息字典
    """
    async def _get_stats(sess: AsyncSession) -> dict[str, Any]:
        # 按状态统计
        status_result = await sess.execute(
            select(ScenarioRun.status, func.count(ScenarioRun.id))
            .group_by(ScenarioRun.status)
        )
        status_counts = dict(status_result.all())

        # 总数
        total_result = await sess.execute(
            select(func.count(ScenarioRun.id))
        )
        total = total_result.scalar() or 0

        # 今日执行数
        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        today_result = await sess.execute(
            select(func.count(ScenarioRun.id)).where(
                ScenarioRun.created_at >= today
            )
        )
        today_count = today_result.scalar() or 0

        return {
            "total": total,
            "today": today_count,
            "by_status": status_counts,
        }

    if session:
        return await _get_stats(session)

    async with get_session_context() as ctx_session:
        return await _get_stats(ctx_session)