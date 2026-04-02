"""
报告服务模块。

提供 Report 的管理操作。
"""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Report, ScenarioRun, get_session_context


async def create_report(
    run_id: int,
    markdown_path: str | None = None,
    html_path: str | None = None,
    summary: dict[str, Any] | None = None,
    session: AsyncSession | None = None,
) -> Report:
    """
    创建报告记录。

    如果该执行记录已有报告，则会更新现有报告。

    Args:
        run_id: 执行记录ID
        markdown_path: Markdown报告文件路径
        html_path: HTML报告文件路径
        summary: 摘要字典
        session: 数据库会话（可选）

    Returns:
        创建或更新的报告实例
    """
    async def _create_or_update(sess: AsyncSession) -> Report:
        # 检查是否已存在报告
        result = await sess.execute(
            select(Report).where(Report.scenario_run_id == run_id)
        )
        report = result.scalar_one_or_none()

        if report:
            # 更新现有报告
            if markdown_path is not None:
                report.markdown_path = markdown_path
            if html_path is not None:
                report.html_path = html_path
            if summary is not None:
                report.summary_json = json.dumps(summary, ensure_ascii=False)
        else:
            # 创建新报告
            report = Report(
                scenario_run_id=run_id,
                markdown_path=markdown_path,
                html_path=html_path,
                summary_json=json.dumps(summary, ensure_ascii=False) if summary else None,
            )
            sess.add(report)

        await sess.flush()
        await sess.refresh(report)
        return report

    if session:
        return await _create_or_update(session)

    async with get_session_context() as ctx_session:
        return await _create_or_update(ctx_session)


async def get_report(
    report_id: int,
    session: AsyncSession | None = None,
) -> Report | None:
    """
    根据ID获取报告记录。

    Args:
        report_id: 报告ID
        session: 数据库会话（可选）

    Returns:
        报告实例，不存在则返回None
    """
    if session:
        result = await session.execute(
            select(Report).where(Report.id == report_id)
        )
        return result.scalar_one_or_none()

    async with get_session_context() as ctx_session:
        result = await ctx_session.execute(
            select(Report).where(Report.id == report_id)
        )
        return result.scalar_one_or_none()


async def get_report_by_run(
    run_id: int,
    session: AsyncSession | None = None,
) -> Report | None:
    """
    根据执行记录ID获取报告。

    Args:
        run_id: 执行记录ID
        session: 数据库会话（可选）

    Returns:
        报告实例，不存在则返回None
    """
    if session:
        result = await session.execute(
            select(Report).where(Report.scenario_run_id == run_id)
        )
        return result.scalar_one_or_none()

    async with get_session_context() as ctx_session:
        result = await ctx_session.execute(
            select(Report).where(Report.scenario_run_id == run_id)
        )
        return result.scalar_one_or_none()


async def get_report_with_run(
    report_id: int,
    session: AsyncSession | None = None,
) -> dict | None:
    """
    获取报告及其关联的执行记录。

    Args:
        report_id: 报告ID
        session: 数据库会话（可选）

    Returns:
        包含报告和执行记录的字典
    """
    async def _get(sess: AsyncSession) -> dict | None:
        result = await sess.execute(
            select(Report)
            .options(selectinload(Report.scenario_run))
            .where(Report.id == report_id)
        )
        report = result.scalar_one_or_none()

        if not report:
            return None

        return {
            "report": report,
            "run": report.scenario_run,
        }

    if session:
        return await _get(session)

    async with get_session_context() as ctx_session:
        return await _get(ctx_session)


async def list_reports(
    offset: int = 0,
    limit: int = 100,
    session: AsyncSession | None = None,
) -> tuple[list[Report], int]:
    """
    获取报告列表。

    Args:
        offset: 偏移量
        limit: 返回数量限制
        session: 数据库会话（可选）

    Returns:
        元组：(报告列表, 总数)
    """
    async def _list(sess: AsyncSession) -> tuple[list[Report], int]:
        # 查询报告列表
        query = (
            select(Report)
            .options(selectinload(Report.scenario_run))
            .order_by(Report.created_at.desc())
            .offset(offset)
            .limit(limit)
        )

        result = await sess.execute(query)
        reports = list(result.scalars().all())

        # 获取总数
        count_result = await sess.execute(select(func.count(Report.id)))
        total = count_result.scalar() or 0

        return reports, total

    if session:
        return await _list(session)

    async with get_session_context() as ctx_session:
        return await _list(ctx_session)


async def update_report(
    report_id: int,
    updates: dict[str, Any],
    session: AsyncSession | None = None,
) -> Report | None:
    """
    更新报告记录。

    Args:
        report_id: 报告ID
        updates: 更新字段字典
        session: 数据库会话（可选）

    Returns:
        更新后的报告实例，不存在则返回None
    """
    allowed_fields = {"markdown_path", "html_path", "summary_json"}

    filtered_updates = {k: v for k, v in updates.items() if k in allowed_fields}

    if not filtered_updates:
        return await get_report(report_id, session)

    async def _update(sess: AsyncSession) -> Report | None:
        result = await sess.execute(
            select(Report).where(Report.id == report_id)
        )
        report = result.scalar_one_or_none()

        if not report:
            return None

        for key, value in filtered_updates.items():
            if key == "summary_json" and isinstance(value, dict):
                value = json.dumps(value, ensure_ascii=False)
            setattr(report, key, value)

        await sess.flush()
        await sess.refresh(report)
        return report

    if session:
        return await _update(session)

    async with get_session_context() as ctx_session:
        return await _update(ctx_session)


async def delete_report(
    report_id: int,
    delete_files: bool = False,
    session: AsyncSession | None = None,
) -> bool:
    """
    删除报告记录。

    Args:
        report_id: 报告ID
        delete_files: 是否同时删除文件
        session: 数据库会话（可选）

    Returns:
        是否删除成功
    """
    async def _delete(sess: AsyncSession) -> bool:
        result = await sess.execute(
            select(Report).where(Report.id == report_id)
        )
        report = result.scalar_one_or_none()

        if not report:
            return False

        # 如果需要删除文件
        if delete_files:
            for path in [report.markdown_path, report.html_path]:
                if path:
                    try:
                        if os.path.exists(path):
                            os.remove(path)
                    except OSError:
                        pass

        await sess.delete(report)
        return True

    if session:
        return await _delete(session)

    async with get_session_context() as ctx_session:
        return await _delete(ctx_session)


async def get_report_content(
    report_id: int,
    content_type: str = "html",
    session: AsyncSession | None = None,
) -> dict | None:
    """
    获取报告内容。

    Args:
        report_id: 报告ID
        content_type: 内容类型 (html/markdown)
        session: 数据库会话（可选）

    Returns:
        包含报告和内容的字典
    """
    report = await get_report(report_id, session)

    if not report:
        return None

    result = {
        "report": report,
        "content": None,
        "exists": False,
        "content_type": content_type,
    }

    # 确定文件路径
    if content_type == "markdown":
        path = report.markdown_path
    else:
        path = report.html_path

    if path and os.path.exists(path):
        result["exists"] = True
        try:
            with open(path, "r", encoding="utf-8") as f:
                result["content"] = f.read()
        except IOError:
            pass

    return result


async def get_report_summary(
    report_id: int,
    session: AsyncSession | None = None,
) -> dict | None:
    """
    获取报告摘要。

    Args:
        report_id: 报告ID
        session: 数据库会话（可选）

    Returns:
        摘要字典，不存在则返回None
    """
    report = await get_report(report_id, session)

    if not report or not report.summary_json:
        return None

    try:
        return json.loads(report.summary_json)
    except json.JSONDecodeError:
        return None


async def ensure_report_directory(
    run_id: int,
    base_dir: str = "reports",
) -> Path:
    """
    确保报告目录存在。

    Args:
        run_id: 执行记录ID
        base_dir: 基础报告目录

    Returns:
        报告目录路径
    """
    report_dir = Path(base_dir) / str(run_id)
    report_dir.mkdir(parents=True, exist_ok=True)
    return report_dir


async def create_report_paths(
    run_id: int,
    base_dir: str = "reports",
) -> dict[str, Path]:
    """
    创建报告文件路径。

    Args:
        run_id: 执行记录ID
        base_dir: 基础报告目录

    Returns:
        包含 markdown_path 和 html_path 的字典
    """
    report_dir = await ensure_report_directory(run_id, base_dir)
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")

    return {
        "markdown_path": report_dir / f"report_{timestamp}.md",
        "html_path": report_dir / f"report_{timestamp}.html",
    }


async def get_report_statistics(
    session: AsyncSession | None = None,
) -> dict[str, Any]:
    """
    获取报告统计信息。

    Args:
        session: 数据库会话（可选）

    Returns:
        统计信息字典
    """
    async def _get_stats(sess: AsyncSession) -> dict[str, Any]:
        # 总报告数
        total_result = await sess.execute(select(func.count(Report.id)))
        total = total_result.scalar() or 0

        # 今日报告数
        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        today_result = await sess.execute(
            select(func.count(Report.id)).where(Report.created_at >= today)
        )
        today_count = today_result.scalar() or 0

        # 本周报告数
        week_start = today - timedelta(days=today.weekday())
        week_result = await sess.execute(
            select(func.count(Report.id)).where(Report.created_at >= week_start)
        )
        week_count = week_result.scalar() or 0

        return {
            "total": total,
            "today": today_count,
            "this_week": week_count,
        }

    if session:
        return await _get_stats(session)

    async with get_session_context() as ctx_session:
        return await _get_stats(ctx_session)