"""
执行产物服务模块。

提供 Artifact 的管理操作。
"""

import json
import os
from pathlib import Path
from typing import Any

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Artifact, ArtifactType, ScenarioRun, ScenarioStep, get_session_context


async def save_artifact(
    run_id: int,
    artifact_type: str,
    path: str,
    size: int | None = None,
    meta: dict[str, Any] | None = None,
    step_id: int | None = None,
    session: AsyncSession | None = None,
) -> Artifact:
    """
    保存执行产物记录。

    Args:
        run_id: 执行记录ID
        artifact_type: 产物类型
        path: 文件路径
        size: 文件大小（字节），可选，不传则自动获取
        meta: 元数据字典
        step_id: 关联的步骤ID
        session: 数据库会话（可选）

    Returns:
        创建的产物记录实例

    Raises:
        FileNotFoundError: 如果文件不存在且需要获取大小
    """
    # 如果未提供文件大小，尝试从文件系统获取
    if size is None and os.path.exists(path):
        size = os.path.getsize(path)

    artifact = Artifact(
        scenario_run_id=run_id,
        step_id=step_id,
        artifact_type=artifact_type,
        path=path,
        size=size,
        meta_json=json.dumps(meta, ensure_ascii=False) if meta else None,
    )

    if session:
        session.add(artifact)
        await session.flush()
        await session.refresh(artifact)
        return artifact

    async with get_session_context() as ctx_session:
        ctx_session.add(artifact)
        await ctx_session.flush()
        await ctx_session.refresh(artifact)
        return artifact


async def get_artifact(
    artifact_id: int,
    session: AsyncSession | None = None,
) -> Artifact | None:
    """
    根据ID获取产物记录。

    Args:
        artifact_id: 产物ID
        session: 数据库会话（可选）

    Returns:
        产物记录实例，不存在则返回None
    """
    if session:
        result = await session.execute(
            select(Artifact).where(Artifact.id == artifact_id)
        )
        return result.scalar_one_or_none()

    async with get_session_context() as ctx_session:
        result = await ctx_session.execute(
            select(Artifact).where(Artifact.id == artifact_id)
        )
        return result.scalar_one_or_none()


async def list_artifacts(
    run_id: int,
    artifact_type: str | None = None,
    step_id: int | None = None,
    session: AsyncSession | None = None,
) -> list[Artifact]:
    """
    获取执行记录的产物列表。

    Args:
        run_id: 执行记录ID
        artifact_type: 产物类型筛选（可选）
        step_id: 步骤ID筛选（可选）
        session: 数据库会话（可选）

    Returns:
        产物列表
    """
    async def _list(sess: AsyncSession) -> list[Artifact]:
        query = select(Artifact).where(Artifact.scenario_run_id == run_id)

        if artifact_type:
            query = query.where(Artifact.artifact_type == artifact_type)

        if step_id is not None:
            query = query.where(Artifact.step_id == step_id)

        query = query.order_by(Artifact.created_at)

        result = await sess.execute(query)
        return list(result.scalars().all())

    if session:
        return await _list(session)

    async with get_session_context() as ctx_session:
        return await _list(ctx_session)


async def get_artifact_path(
    artifact_id: int,
    session: AsyncSession | None = None,
) -> str | None:
    """
    获取产物文件路径。

    Args:
        artifact_id: 产物ID
        session: 数据库会话（可选）

    Returns:
        文件路径，不存在则返回None
    """
    artifact = await get_artifact(artifact_id, session)
    return artifact.path if artifact else None


async def get_artifact_with_content(
    artifact_id: int,
    session: AsyncSession | None = None,
) -> dict | None:
    """
    获取产物记录及其文件内容（适用于文本类型产物）。

    Args:
        artifact_id: 产物ID
        session: 数据库会话（可选）

    Returns:
        包含产物信息和内容的字典
    """
    artifact = await get_artifact(artifact_id, session)

    if not artifact:
        return None

    result = {
        "artifact": artifact,
        "content": None,
        "exists": False,
    }

    if os.path.exists(artifact.path):
        result["exists"] = True
        # 对于文本类型的产物，尝试读取内容
        text_types = {
            ArtifactType.LOGCAT.value,
            ArtifactType.GETPROP.value,
            ArtifactType.STDOUT.value,
            ArtifactType.STDERR.value,
            ArtifactType.SUMMARY.value,
        }

        if artifact.artifact_type in text_types:
            try:
                with open(artifact.path, "r", encoding="utf-8") as f:
                    result["content"] = f.read()
            except (UnicodeDecodeError, IOError):
                # 如果读取失败，保持 content 为 None
                pass

    return result


async def delete_artifact(
    artifact_id: int,
    delete_file: bool = False,
    session: AsyncSession | None = None,
) -> bool:
    """
    删除产物记录。

    Args:
        artifact_id: 产物ID
        delete_file: 是否同时删除文件
        session: 数据库会话（可选）

    Returns:
        是否删除成功
    """
    async def _delete(sess: AsyncSession) -> bool:
        result = await sess.execute(
            select(Artifact).where(Artifact.id == artifact_id)
        )
        artifact = result.scalar_one_or_none()

        if not artifact:
            return False

        # 如果需要删除文件
        if delete_file and artifact.path:
            try:
                if os.path.exists(artifact.path):
                    os.remove(artifact.path)
            except OSError:
                # 文件删除失败不影响记录删除
                pass

        await sess.delete(artifact)
        return True

    if session:
        return await _delete(session)

    async with get_session_context() as ctx_session:
        return await _delete(ctx_session)


async def delete_run_artifacts(
    run_id: int,
    delete_files: bool = False,
    session: AsyncSession | None = None,
) -> int:
    """
    删除执行记录的所有产物。

    Args:
        run_id: 执行记录ID
        delete_files: 是否同时删除文件
        session: 数据库会话（可选）

    Returns:
        删除的产物数量
    """
    async def _delete(sess: AsyncSession) -> int:
        # 获取所有产物
        result = await sess.execute(
            select(Artifact).where(Artifact.scenario_run_id == run_id)
        )
        artifacts = list(result.scalars().all())

        count = 0

        for artifact in artifacts:
            if delete_files and artifact.path:
                try:
                    if os.path.exists(artifact.path):
                        os.remove(artifact.path)
                except OSError:
                    pass

            await sess.delete(artifact)
            count += 1

        return count

    if session:
        return await _delete(session)

    async with get_session_context() as ctx_session:
        return await _delete(ctx_session)


async def get_artifacts_by_type(
    run_id: int,
    artifact_type: str,
    session: AsyncSession | None = None,
) -> list[Artifact]:
    """
    获取执行记录指定类型的产物列表。

    Args:
        run_id: 执行记录ID
        artifact_type: 产物类型
        session: 数据库会话（可选）

    Returns:
        指定类型的产物列表
    """
    return await list_artifacts(run_id, artifact_type=artifact_type, session=session)


async def get_artifact_statistics(
    run_id: int,
    session: AsyncSession | None = None,
) -> dict[str, Any]:
    """
    获取执行记录的产物统计信息。

    Args:
        run_id: 执行记录ID
        session: 数据库会话（可选）

    Returns:
        统计信息字典
    """
    async def _get_stats(sess: AsyncSession) -> dict[str, Any]:
        # 按类型统计
        type_result = await sess.execute(
            select(Artifact.artifact_type, func.count(Artifact.id), func.sum(Artifact.size))
            .where(Artifact.scenario_run_id == run_id)
            .group_by(Artifact.artifact_type)
        )

        type_stats = {}
        total_count = 0
        total_size = 0

        for row in type_result:
            artifact_type, count, size = row
            type_stats[artifact_type] = {
                "count": count,
                "total_size": size or 0,
            }
            total_count += count
            total_size += size or 0

        return {
            "total_count": total_count,
            "total_size": total_size,
            "by_type": type_stats,
        }

    if session:
        return await _get_stats(session)

    async with get_session_context() as ctx_session:
        return await _get_stats(ctx_session)


async def ensure_artifact_directory(
    run_id: int,
    base_dir: str = "artifacts",
) -> Path:
    """
    确保产物目录存在。

    Args:
        run_id: 执行记录ID
        base_dir: 基础产物目录

    Returns:
        产物目录路径
    """
    artifact_dir = Path(base_dir) / str(run_id)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    return artifact_dir


async def create_artifact_path(
    run_id: int,
    artifact_type: str,
    filename: str,
    base_dir: str = "artifacts",
) -> Path:
    """
    创建产物文件路径。

    Args:
        run_id: 执行记录ID
        artifact_type: 产物类型
        filename: 文件名
        base_dir: 基础产物目录

    Returns:
        完整文件路径
    """
    artifact_dir = await ensure_artifact_directory(run_id, base_dir)
    return artifact_dir / f"{artifact_type}_{filename}"