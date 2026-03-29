"""
配置文件服务模块。

提供 FaultProfile、ValidationProfile 和 RecoveryProfile 的 CRUD 操作。
"""

from typing import Any, Literal

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from chaosdroid.models import (
    FaultProfile,
    RecoveryProfile,
    RiskLevel,
    ValidationProfile,
    get_session_context,
)

# 定义配置文件类型
ProfileType = Literal["fault", "validation", "recovery"]

# 模型映射
PROFILE_MODEL_MAP: dict[ProfileType, type] = {
    "fault": FaultProfile,
    "validation": ValidationProfile,
    "recovery": RecoveryProfile,
}


class ProfileFilters:
    """配置文件筛选条件。"""

    def __init__(
        self,
        name: str | None = None,
        risk_level: str | None = None,  # 仅用于 FaultProfile
    ):
        self.name = name
        self.risk_level = risk_level


# ==================== FaultProfile CRUD ====================


async def create_fault_profile(
    name: str,
    fault_type: str,
    parameters_json: str | None = None,
    safe_cleanup_required: bool = False,
    risk_level: str = RiskLevel.LOW.value,
    description: str | None = None,
    session: AsyncSession | None = None,
) -> FaultProfile:
    """
    创建故障配置。

    Args:
        name: 配置名称
        fault_type: 故障类型 (storage_pressure/low_battery/network_jitter/reboot_timeout/cpu_io_stress/monkey_stability)
        parameters_json: 参数JSON
        safe_cleanup_required: 是否需要安全清理
        risk_level: 风险等级
        description: 配置描述
        session: 数据库会话（可选）

    Returns:
        创建的故障配置实例
    """
    profile = FaultProfile(
        name=name,
        fault_type=fault_type,
        parameters_json=parameters_json,
        safe_cleanup_required=safe_cleanup_required,
        risk_level=risk_level,
        description=description,
    )

    if session:
        session.add(profile)
        await session.flush()
        await session.refresh(profile)
        return profile

    async with get_session_context() as ctx_session:
        ctx_session.add(profile)
        await ctx_session.flush()
        await ctx_session.refresh(profile)
        return profile


async def get_fault_profile(
    profile_id: int,
    session: AsyncSession | None = None,
) -> FaultProfile | None:
    """
    根据ID获取故障配置。

    Args:
        profile_id: 配置ID
        session: 数据库会话（可选）

    Returns:
        故障配置实例，不存在则返回None
    """
    if session:
        result = await session.execute(
            select(FaultProfile).where(FaultProfile.id == profile_id)
        )
        return result.scalar_one_or_none()

    async with get_session_context() as ctx_session:
        result = await ctx_session.execute(
            select(FaultProfile).where(FaultProfile.id == profile_id)
        )
        return result.scalar_one_or_none()


async def list_fault_profiles(
    filters: ProfileFilters | None = None,
    offset: int = 0,
    limit: int = 100,
    session: AsyncSession | None = None,
) -> tuple[list[FaultProfile], int]:
    """
    获取故障配置列表。

    Args:
        filters: 筛选条件
        offset: 偏移量
        limit: 返回数量限制
        session: 数据库会话（可选）

    Returns:
        元组：(故障配置列表, 总数)
    """
    async def _execute_query(sess: AsyncSession) -> tuple[list[FaultProfile], int]:
        query = select(FaultProfile)
        count_query = select(func.count(FaultProfile.id))

        if filters:
            conditions = []

            if filters.name:
                conditions.append(FaultProfile.name.ilike(f"%{filters.name}%"))

            if filters.risk_level:
                conditions.append(FaultProfile.risk_level == filters.risk_level)

            if conditions:
                query = query.where(and_(*conditions))
                count_query = count_query.where(and_(*conditions))

        query = query.order_by(FaultProfile.updated_at.desc())
        query = query.offset(offset).limit(limit)

        result = await sess.execute(query)
        profiles = list(result.scalars().all())

        count_result = await sess.execute(count_query)
        total = count_result.scalar() or 0

        return profiles, total

    if session:
        return await _execute_query(session)

    async with get_session_context() as ctx_session:
        return await _execute_query(ctx_session)


async def update_fault_profile(
    profile_id: int,
    updates: dict[str, Any],
    session: AsyncSession | None = None,
) -> FaultProfile | None:
    """
    更新故障配置。

    Args:
        profile_id: 配置ID
        updates: 更新字段字典
        session: 数据库会话（可选）

    Returns:
        更新后的故障配置实例，不存在则返回None
    """
    allowed_fields = {
        "name",
        "fault_type",
        "parameters_json",
        "safe_cleanup_required",
        "risk_level",
        "description",
    }

    filtered_updates = {k: v for k, v in updates.items() if k in allowed_fields}

    if not filtered_updates:
        return await get_fault_profile(profile_id, session)

    async def _update(sess: AsyncSession) -> FaultProfile | None:
        result = await sess.execute(
            select(FaultProfile).where(FaultProfile.id == profile_id)
        )
        profile = result.scalar_one_or_none()

        if not profile:
            return None

        for key, value in filtered_updates.items():
            setattr(profile, key, value)

        await sess.flush()
        await sess.refresh(profile)
        return profile

    if session:
        return await _update(session)

    async with get_session_context() as ctx_session:
        return await _update(ctx_session)


async def delete_fault_profile(
    profile_id: int,
    session: AsyncSession | None = None,
) -> bool:
    """
    删除故障配置。

    Args:
        profile_id: 配置ID
        session: 数据库会话（可选）

    Returns:
        是否删除成功
    """
    async def _delete(sess: AsyncSession) -> bool:
        result = await sess.execute(
            select(FaultProfile).where(FaultProfile.id == profile_id)
        )
        profile = result.scalar_one_or_none()

        if not profile:
            return False

        await sess.delete(profile)
        return True

    if session:
        return await _delete(session)

    async with get_session_context() as ctx_session:
        return await _delete(ctx_session)


# ==================== ValidationProfile CRUD ====================


async def create_validation_profile(
    name: str,
    checks_json: str | None = None,
    timeout_sec: int = 180,
    pass_rules_json: str | None = None,
    description: str | None = None,
    session: AsyncSession | None = None,
) -> ValidationProfile:
    """
    创建验证配置。

    Args:
        name: 配置名称
        checks_json: 检查项JSON
        timeout_sec: 超时时间（秒）
        pass_rules_json: 通过规则JSON
        description: 配置描述
        session: 数据库会话（可选）

    Returns:
        创建的验证配置实例
    """
    profile = ValidationProfile(
        name=name,
        checks_json=checks_json,
        timeout_sec=timeout_sec,
        pass_rules_json=pass_rules_json,
        description=description,
    )

    if session:
        session.add(profile)
        await session.flush()
        await session.refresh(profile)
        return profile

    async with get_session_context() as ctx_session:
        ctx_session.add(profile)
        await ctx_session.flush()
        await ctx_session.refresh(profile)
        return profile


async def get_validation_profile(
    profile_id: int,
    session: AsyncSession | None = None,
) -> ValidationProfile | None:
    """
    根据ID获取验证配置。

    Args:
        profile_id: 配置ID
        session: 数据库会话（可选）

    Returns:
        验证配置实例，不存在则返回None
    """
    if session:
        result = await session.execute(
            select(ValidationProfile).where(ValidationProfile.id == profile_id)
        )
        return result.scalar_one_or_none()

    async with get_session_context() as ctx_session:
        result = await ctx_session.execute(
            select(ValidationProfile).where(ValidationProfile.id == profile_id)
        )
        return result.scalar_one_or_none()


async def list_validation_profiles(
    filters: ProfileFilters | None = None,
    offset: int = 0,
    limit: int = 100,
    session: AsyncSession | None = None,
) -> tuple[list[ValidationProfile], int]:
    """
    获取验证配置列表。

    Args:
        filters: 筛选条件
        offset: 偏移量
        limit: 返回数量限制
        session: 数据库会话（可选）

    Returns:
        元组：(验证配置列表, 总数)
    """
    async def _execute_query(sess: AsyncSession) -> tuple[list[ValidationProfile], int]:
        query = select(ValidationProfile)
        count_query = select(func.count(ValidationProfile.id))

        if filters and filters.name:
            query = query.where(ValidationProfile.name.ilike(f"%{filters.name}%"))
            count_query = count_query.where(
                ValidationProfile.name.ilike(f"%{filters.name}%")
            )

        query = query.order_by(ValidationProfile.updated_at.desc())
        query = query.offset(offset).limit(limit)

        result = await sess.execute(query)
        profiles = list(result.scalars().all())

        count_result = await sess.execute(count_query)
        total = count_result.scalar() or 0

        return profiles, total

    if session:
        return await _execute_query(session)

    async with get_session_context() as ctx_session:
        return await _execute_query(ctx_session)


async def update_validation_profile(
    profile_id: int,
    updates: dict[str, Any],
    session: AsyncSession | None = None,
) -> ValidationProfile | None:
    """
    更新验证配置。

    Args:
        profile_id: 配置ID
        updates: 更新字段字典
        session: 数据库会话（可选）

    Returns:
        更新后的验证配置实例，不存在则返回None
    """
    allowed_fields = {"name", "checks_json", "timeout_sec", "pass_rules_json", "description"}

    filtered_updates = {k: v for k, v in updates.items() if k in allowed_fields}

    if not filtered_updates:
        return await get_validation_profile(profile_id, session)

    async def _update(sess: AsyncSession) -> ValidationProfile | None:
        result = await sess.execute(
            select(ValidationProfile).where(ValidationProfile.id == profile_id)
        )
        profile = result.scalar_one_or_none()

        if not profile:
            return None

        for key, value in filtered_updates.items():
            setattr(profile, key, value)

        await sess.flush()
        await sess.refresh(profile)
        return profile

    if session:
        return await _update(session)

    async with get_session_context() as ctx_session:
        return await _update(ctx_session)


async def delete_validation_profile(
    profile_id: int,
    session: AsyncSession | None = None,
) -> bool:
    """
    删除验证配置。

    Args:
        profile_id: 配置ID
        session: 数据库会话（可选）

    Returns:
        是否删除成功
    """
    async def _delete(sess: AsyncSession) -> bool:
        result = await sess.execute(
            select(ValidationProfile).where(ValidationProfile.id == profile_id)
        )
        profile = result.scalar_one_or_none()

        if not profile:
            return False

        await sess.delete(profile)
        return True

    if session:
        return await _delete(session)

    async with get_session_context() as ctx_session:
        return await _delete(ctx_session)


# ==================== RecoveryProfile CRUD ====================


async def create_recovery_profile(
    name: str,
    steps_json: str | None = None,
    manual_intervention_allowed: bool = True,
    timeout_sec: int = 300,
    description: str | None = None,
    session: AsyncSession | None = None,
) -> RecoveryProfile:
    """
    创建恢复配置。

    Args:
        name: 配置名称
        steps_json: 恢复步骤JSON
        manual_intervention_allowed: 是否允许人工介入
        timeout_sec: 超时时间（秒）
        description: 配置描述
        session: 数据库会话（可选）

    Returns:
        创建的恢复配置实例
    """
    profile = RecoveryProfile(
        name=name,
        steps_json=steps_json,
        manual_intervention_allowed=manual_intervention_allowed,
        timeout_sec=timeout_sec,
        description=description,
    )

    if session:
        session.add(profile)
        await session.flush()
        await session.refresh(profile)
        return profile

    async with get_session_context() as ctx_session:
        ctx_session.add(profile)
        await ctx_session.flush()
        await ctx_session.refresh(profile)
        return profile


async def get_recovery_profile(
    profile_id: int,
    session: AsyncSession | None = None,
) -> RecoveryProfile | None:
    """
    根据ID获取恢复配置。

    Args:
        profile_id: 配置ID
        session: 数据库会话（可选）

    Returns:
        恢复配置实例，不存在则返回None
    """
    if session:
        result = await session.execute(
            select(RecoveryProfile).where(RecoveryProfile.id == profile_id)
        )
        return result.scalar_one_or_none()

    async with get_session_context() as ctx_session:
        result = await ctx_session.execute(
            select(RecoveryProfile).where(RecoveryProfile.id == profile_id)
        )
        return result.scalar_one_or_none()


async def list_recovery_profiles(
    filters: ProfileFilters | None = None,
    offset: int = 0,
    limit: int = 100,
    session: AsyncSession | None = None,
) -> tuple[list[RecoveryProfile], int]:
    """
    获取恢复配置列表。

    Args:
        filters: 筛选条件
        offset: 偏移量
        limit: 返回数量限制
        session: 数据库会话（可选）

    Returns:
        元组：(恢复配置列表, 总数)
    """
    async def _execute_query(sess: AsyncSession) -> tuple[list[RecoveryProfile], int]:
        query = select(RecoveryProfile)
        count_query = select(func.count(RecoveryProfile.id))

        if filters and filters.name:
            query = query.where(RecoveryProfile.name.ilike(f"%{filters.name}%"))
            count_query = count_query.where(RecoveryProfile.name.ilike(f"%{filters.name}%"))

        query = query.order_by(RecoveryProfile.updated_at.desc())
        query = query.offset(offset).limit(limit)

        result = await sess.execute(query)
        profiles = list(result.scalars().all())

        count_result = await sess.execute(count_query)
        total = count_result.scalar() or 0

        return profiles, total

    if session:
        return await _execute_query(session)

    async with get_session_context() as ctx_session:
        return await _execute_query(ctx_session)


async def update_recovery_profile(
    profile_id: int,
    updates: dict[str, Any],
    session: AsyncSession | None = None,
) -> RecoveryProfile | None:
    """
    更新恢复配置。

    Args:
        profile_id: 配置ID
        updates: 更新字段字典
        session: 数据库会话（可选）

    Returns:
        更新后的恢复配置实例，不存在则返回None
    """
    allowed_fields = {
        "name",
        "steps_json",
        "manual_intervention_allowed",
        "timeout_sec",
        "description",
    }

    filtered_updates = {k: v for k, v in updates.items() if k in allowed_fields}

    if not filtered_updates:
        return await get_recovery_profile(profile_id, session)

    async def _update(sess: AsyncSession) -> RecoveryProfile | None:
        result = await sess.execute(
            select(RecoveryProfile).where(RecoveryProfile.id == profile_id)
        )
        profile = result.scalar_one_or_none()

        if not profile:
            return None

        for key, value in filtered_updates.items():
            setattr(profile, key, value)

        await sess.flush()
        await sess.refresh(profile)
        return profile

    if session:
        return await _update(session)

    async with get_session_context() as ctx_session:
        return await _update(ctx_session)


async def delete_recovery_profile(
    profile_id: int,
    session: AsyncSession | None = None,
) -> bool:
    """
    删除恢复配置。

    Args:
        profile_id: 配置ID
        session: 数据库会话（可选）

    Returns:
        是否删除成功
    """
    async def _delete(sess: AsyncSession) -> bool:
        result = await sess.execute(
            select(RecoveryProfile).where(RecoveryProfile.id == profile_id)
        )
        profile = result.scalar_one_or_none()

        if not profile:
            return False

        await sess.delete(profile)
        return True

    if session:
        return await _delete(session)

    async with get_session_context() as ctx_session:
        return await _delete(ctx_session)


# ==================== 通用 Profile 操作 ====================


async def list_profiles(
    profile_type: ProfileType,
    filters: ProfileFilters | None = None,
    offset: int = 0,
    limit: int = 100,
    session: AsyncSession | None = None,
) -> tuple[list, int]:
    """
    获取指定类型的配置文件列表。

    Args:
        profile_type: 配置文件类型 (fault/validation/recovery)
        filters: 筛选条件
        offset: 偏移量
        limit: 返回数量限制
        session: 数据库会话（可选）

    Returns:
        元组：(配置文件列表, 总数)

    Raises:
        ValueError: 无效的配置文件类型
    """
    if profile_type == "fault":
        return await list_fault_profiles(filters, offset, limit, session)
    elif profile_type == "validation":
        return await list_validation_profiles(filters, offset, limit, session)
    elif profile_type == "recovery":
        return await list_recovery_profiles(filters, offset, limit, session)
    else:
        raise ValueError(f"无效的配置文件类型: {profile_type}")


async def get_profile(
    profile_type: ProfileType,
    profile_id: int,
    session: AsyncSession | None = None,
):
    """
    根据ID获取指定类型的配置文件。

    Args:
        profile_type: 配置文件类型 (fault/validation/recovery)
        profile_id: 配置ID
        session: 数据库会话（可选）

    Returns:
        配置文件实例，不存在则返回None

    Raises:
        ValueError: 无效的配置文件类型
    """
    if profile_type == "fault":
        return await get_fault_profile(profile_id, session)
    elif profile_type == "validation":
        return await get_validation_profile(profile_id, session)
    elif profile_type == "recovery":
        return await get_recovery_profile(profile_id, session)
    else:
        raise ValueError(f"无效的配置文件类型: {profile_type}")