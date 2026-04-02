"""
场景模板服务模块。

提供 ScenarioTemplate 的 CRUD 操作。
"""

from datetime import datetime
from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    ExecutorMode,
    InjectStage,
    RunStatus,
    ScenarioRun,
    ScenarioTemplate,
    TargetType,
    get_session_context,
)


class ScenarioFilters:
    """场景筛选条件。"""

    def __init__(
        self,
        name: str | None = None,
        target_type: str | None = None,
        inject_stage: str | None = None,
        executor_mode: str | None = None,
        enabled: bool | None = None,
        fault_profile_id: int | None = None,
        validation_profile_id: int | None = None,
        recovery_profile_id: int | None = None,
    ):
        self.name = name
        self.target_type = target_type
        self.inject_stage = inject_stage
        self.executor_mode = executor_mode
        self.enabled = enabled
        self.fault_profile_id = fault_profile_id
        self.validation_profile_id = validation_profile_id
        self.recovery_profile_id = recovery_profile_id


async def create_scenario(
    name: str,
    description: str | None = None,
    target_type: str = TargetType.STABILITY.value,
    fault_profile_id: int | None = None,
    inject_stage: str = InjectStage.PRECHECK.value,
    validation_profile_id: int | None = None,
    recovery_profile_id: int | None = None,
    executor_mode: str = ExecutorMode.MOCK.value,
    enabled: bool = True,
    session: AsyncSession | None = None,
) -> ScenarioTemplate:
    """
    创建场景模板。

    Args:
        name: 场景名称
        description: 场景描述
        target_type: 目标类型 (upgrade/stability/monkey/recovery)
        fault_profile_id: 关联故障配置ID
        inject_stage: 注入阶段
        validation_profile_id: 关联验证配置ID
        recovery_profile_id: 关联恢复配置ID
        executor_mode: 执行器模式 (real/mock)
        enabled: 是否启用
        session: 数据库会话（可选，不传则使用上下文管理器）

    Returns:
        创建的场景模板实例
    """
    scenario = ScenarioTemplate(
        name=name,
        description=description,
        target_type=target_type,
        fault_profile_id=fault_profile_id,
        inject_stage=inject_stage,
        validation_profile_id=validation_profile_id,
        recovery_profile_id=recovery_profile_id,
        executor_mode=executor_mode,
        enabled=enabled,
    )

    if session:
        session.add(scenario)
        await session.flush()
        await session.refresh(scenario)
        return scenario

    async with get_session_context() as ctx_session:
        ctx_session.add(scenario)
        await ctx_session.flush()
        await ctx_session.refresh(scenario)
        return scenario


async def get_scenario(
    scenario_id: int,
    session: AsyncSession | None = None,
) -> ScenarioTemplate | None:
    """
    根据ID获取场景模板。

    Args:
        scenario_id: 场景模板ID
        session: 数据库会话（可选）

    Returns:
        场景模板实例，不存在则返回None
    """
    if session:
        result = await session.execute(
            select(ScenarioTemplate).where(ScenarioTemplate.id == scenario_id)
        )
        return result.scalar_one_or_none()

    async with get_session_context() as ctx_session:
        result = await ctx_session.execute(
            select(ScenarioTemplate).where(ScenarioTemplate.id == scenario_id)
        )
        return result.scalar_one_or_none()


async def list_scenarios(
    filters: ScenarioFilters | None = None,
    offset: int = 0,
    limit: int = 100,
    session: AsyncSession | None = None,
) -> tuple[list[ScenarioTemplate], int]:
    """
    获取场景模板列表。

    Args:
        filters: 筛选条件
        offset: 偏移量
        limit: 返回数量限制
        session: 数据库会话（可选）

    Returns:
        元组：(场景模板列表, 总数)
    """
    async def _execute_query(sess: AsyncSession) -> tuple[list[ScenarioTemplate], int]:
        # 构建基础查询
        query = select(ScenarioTemplate)
        count_query = select(func.count(ScenarioTemplate.id))

        # 应用筛选条件
        if filters:
            conditions = []

            if filters.name:
                conditions.append(ScenarioTemplate.name.ilike(f"%{filters.name}%"))

            if filters.target_type:
                conditions.append(ScenarioTemplate.target_type == filters.target_type)

            if filters.inject_stage:
                conditions.append(ScenarioTemplate.inject_stage == filters.inject_stage)

            if filters.executor_mode:
                conditions.append(ScenarioTemplate.executor_mode == filters.executor_mode)

            if filters.enabled is not None:
                conditions.append(ScenarioTemplate.enabled == filters.enabled)

            if filters.fault_profile_id:
                conditions.append(ScenarioTemplate.fault_profile_id == filters.fault_profile_id)

            if filters.validation_profile_id:
                conditions.append(
                    ScenarioTemplate.validation_profile_id == filters.validation_profile_id
                )

            if filters.recovery_profile_id:
                conditions.append(
                    ScenarioTemplate.recovery_profile_id == filters.recovery_profile_id
                )

            if conditions:
                query = query.where(and_(*conditions))
                count_query = count_query.where(and_(*conditions))

        # 排序：按更新时间倒序
        query = query.order_by(ScenarioTemplate.updated_at.desc())

        # 分页
        query = query.offset(offset).limit(limit)

        # 执行查询
        result = await sess.execute(query)
        scenarios = list(result.scalars().all())

        # 获取总数
        count_result = await sess.execute(count_query)
        total = count_result.scalar() or 0

        return scenarios, total

    if session:
        return await _execute_query(session)

    async with get_session_context() as ctx_session:
        return await _execute_query(ctx_session)


async def update_scenario(
    scenario_id: int,
    updates: dict[str, Any],
    session: AsyncSession | None = None,
) -> ScenarioTemplate | None:
    """
    更新场景模板。

    Args:
        scenario_id: 场景模板ID
        updates: 更新字段字典
        session: 数据库会话（可选）

    Returns:
        更新后的场景模板实例，不存在则返回None
    """
    # 允许更新的字段
    allowed_fields = {
        "name",
        "description",
        "target_type",
        "fault_profile_id",
        "inject_stage",
        "validation_profile_id",
        "recovery_profile_id",
        "executor_mode",
        "enabled",
    }

    # 过滤不允许更新的字段
    filtered_updates = {k: v for k, v in updates.items() if k in allowed_fields}

    if not filtered_updates:
        return await get_scenario(scenario_id, session)

    async def _update(sess: AsyncSession) -> ScenarioTemplate | None:
        # 查询场景
        result = await sess.execute(
            select(ScenarioTemplate).where(ScenarioTemplate.id == scenario_id)
        )
        scenario = result.scalar_one_or_none()

        if not scenario:
            return None

        # 更新字段
        for key, value in filtered_updates.items():
            setattr(scenario, key, value)

        await sess.flush()
        await sess.refresh(scenario)
        return scenario

    if session:
        return await _update(session)

    async with get_session_context() as ctx_session:
        return await _update(ctx_session)


async def delete_scenario(
    scenario_id: int,
    session: AsyncSession | None = None,
) -> bool:
    """
    删除场景模板。

    Args:
        scenario_id: 场景模板ID
        session: 数据库会话（可选）

    Returns:
        是否删除成功
    """
    async def _delete(sess: AsyncSession) -> bool:
        # 查询场景
        result = await sess.execute(
            select(ScenarioTemplate).where(ScenarioTemplate.id == scenario_id)
        )
        scenario = result.scalar_one_or_none()

        if not scenario:
            return False

        await sess.delete(scenario)
        return True

    if session:
        return await _delete(session)

    async with get_session_context() as ctx_session:
        return await _delete(ctx_session)


async def clone_scenario(
    scenario_id: int,
    new_name: str | None = None,
    session: AsyncSession | None = None,
) -> ScenarioTemplate | None:
    """
    克隆场景模板。

    克隆时会复制所有字段，但：
    - 名称使用原名称 + "-clone" 或用户指定名称
    - 关联的 Profile 不复制，共享引用
    - 设置 enabled=False，需用户手动启用

    Args:
        scenario_id: 要克隆的场景模板ID
        new_name: 新场景名称（可选）
        session: 数据库会话（可选）

    Returns:
        克隆的场景模板实例，原场景不存在则返回None
    """
    async def _clone(sess: AsyncSession) -> ScenarioTemplate | None:
        # 查询原场景
        result = await sess.execute(
            select(ScenarioTemplate).where(ScenarioTemplate.id == scenario_id)
        )
        original = result.scalar_one_or_none()

        if not original:
            return None

        # 创建克隆场景
        clone = ScenarioTemplate(
            name=new_name or f"{original.name}-clone",
            description=original.description,
            target_type=original.target_type,
            fault_profile_id=original.fault_profile_id,
            inject_stage=original.inject_stage,
            validation_profile_id=original.validation_profile_id,
            recovery_profile_id=original.recovery_profile_id,
            executor_mode=original.executor_mode,
            enabled=False,  # 克隆的场景默认禁用
        )

        sess.add(clone)
        await sess.flush()
        await sess.refresh(clone)
        return clone

    if session:
        return await _clone(session)

    async with get_session_context() as ctx_session:
        return await _clone(ctx_session)


async def get_scenario_with_runs(
    scenario_id: int,
    run_status: str | None = None,
    session: AsyncSession | None = None,
) -> dict | None:
    """
    获取场景模板及其关联的执行记录。

    Args:
        scenario_id: 场景模板ID
        run_status: 执行记录状态筛选（可选）
        session: 数据库会话（可选）

    Returns:
        包含场景模板和执行记录的字典
    """
    async def _get(sess: AsyncSession) -> dict | None:
        # 查询场景
        result = await sess.execute(
            select(ScenarioTemplate).where(ScenarioTemplate.id == scenario_id)
        )
        scenario = result.scalar_one_or_none()

        if not scenario:
            return None

        # 查询关联的执行记录
        run_query = select(ScenarioRun).where(
            ScenarioRun.scenario_template_id == scenario_id
        )

        if run_status:
            run_query = run_query.where(ScenarioRun.status == run_status)

        run_query = run_query.order_by(ScenarioRun.created_at.desc()).limit(10)

        run_result = await sess.execute(run_query)
        runs = list(run_result.scalars().all())

        return {
            "scenario": scenario,
            "recent_runs": runs,
        }

    if session:
        return await _get(session)

    async with get_session_context() as ctx_session:
        return await _get(ctx_session)