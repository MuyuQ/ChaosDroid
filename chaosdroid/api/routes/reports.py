"""Reports API routes - 连接报告服务层."""

from fastapi import APIRouter, HTTPException, Query, Path
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from typing import Optional
import json
import os

from chaosdroid.services.report_service import (
    create_report,
    get_report,
    get_report_by_run,
    get_report_with_run,
    list_reports,
    update_report,
    delete_report,
    get_report_content,
    get_report_summary,
    get_report_statistics,
)

router = APIRouter()


# ==================== 响应模型 ====================

class ReportResponse(BaseModel):
    """报告响应"""
    id: int
    scenario_run_id: int
    markdown_path: Optional[str]
    html_path: Optional[str]
    summary: Optional[dict]
    created_at: Optional[str]
    updated_at: Optional[str]


class ApiResponse(BaseModel):
    """统一API响应格式"""
    success: bool
    data: Optional[dict] = None
    error: Optional[dict] = None


# ==================== 辅助函数 ====================

def _report_to_dict(report) -> dict:
    """将报告模型转换为字典"""
    return {
        "id": report.id,
        "scenario_run_id": report.scenario_run_id,
        "markdown_path": report.markdown_path,
        "html_path": report.html_path,
        "summary": json.loads(report.summary_json or "{}"),
        "created_at": report.created_at.isoformat() if report.created_at else None,
        "updated_at": report.updated_at.isoformat() if report.updated_at else None,
    }


# ==================== API端点 ====================

@router.get("", response_model=ApiResponse)
async def list_reports_api(
    offset: int = Query(0, ge=0, description="偏移量"),
    limit: int = Query(100, ge=1, le=500, description="返回数量限制"),
):
    """获取报告列表"""
    try:
        reports, total = await list_reports(offset, limit)
        report_list = [_report_to_dict(r) for r in reports]

        return ApiResponse(
            success=True,
            data={
                "reports": report_list,
                "total": total,
                "offset": offset,
                "limit": limit,
            }
        )

    except Exception as e:
        return ApiResponse(
            success=False,
            error={"code": "internal_error", "message": str(e)}
        )


@router.get("/statistics", response_model=ApiResponse)
async def get_report_statistics_api():
    """获取报告统计信息"""
    try:
        stats = await get_report_statistics()

        return ApiResponse(
            success=True,
            data={"statistics": stats}
        )

    except Exception as e:
        return ApiResponse(
            success=False,
            error={"code": "internal_error", "message": str(e)}
        )


@router.get("/{report_id}", response_model=ApiResponse)
async def get_report_api(report_id: int = Path(..., gt=0, description="报告ID")):
    """获取报告元数据"""
    try:
        result = await get_report_with_run(report_id)

        if not result:
            return ApiResponse(
                success=False,
                error={"code": "not_found", "message": f"报告不存在: id={report_id}"}
            )

        report_dict = _report_to_dict(result["report"])
        run = result["run"]

        run_dict = None
        if run:
            run_dict = {
                "id": run.id,
                "device_serial": run.device_serial,
                "status": run.status,
                "started_at": run.started_at.isoformat() if run.started_at else None,
                "finished_at": run.finished_at.isoformat() if run.finished_at else None,
            }

        return ApiResponse(
            success=True,
            data={
                "report": report_dict,
                "run": run_dict,
            }
        )

    except Exception as e:
        return ApiResponse(
            success=False,
            error={"code": "internal_error", "message": str(e)}
        )


@router.get("/{report_id}/summary", response_model=ApiResponse)
async def get_report_summary_api(report_id: int = Path(..., gt=0, description="报告ID")):
    """获取报告摘要"""
    try:
        summary = await get_report_summary(report_id)

        if summary is None:
            # 检查报告是否存在
            report = await get_report(report_id)
            if not report:
                return ApiResponse(
                    success=False,
                    error={"code": "not_found", "message": f"报告不存在: id={report_id}"}
                )
            # 报告存在但没有摘要
            return ApiResponse(
                success=True,
                data={"summary": None, "message": "报告没有摘要数据"}
            )

        return ApiResponse(
            success=True,
            data={"summary": summary}
        )

    except Exception as e:
        return ApiResponse(
            success=False,
            error={"code": "internal_error", "message": str(e)}
        )


@router.get("/{report_id}/html")
async def get_report_html_api(report_id: int = Path(..., gt=0, description="报告ID")):
    """获取HTML报告"""
    try:
        result = await get_report_content(report_id, "html")

        if not result:
            raise HTTPException(status_code=404, detail=f"报告不存在: id={report_id}")

        if not result["exists"]:
            raise HTTPException(
                status_code=404,
                detail=f"HTML报告文件不存在: {result['report'].html_path or '未生成'}"
            )

        # 返回文件内容
        return {
            "success": True,
            "content": result["content"],
            "path": result["report"].html_path,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{report_id}/html/file")
async def get_report_html_file_api(report_id: int = Path(..., gt=0, description="报告ID")):
    """获取HTML报告文件（直接下载）"""
    try:
        result = await get_report_content(report_id, "html")

        if not result:
            raise HTTPException(status_code=404, detail=f"报告不存在: id={report_id}")

        if not result["exists"] or not result["report"].html_path:
            raise HTTPException(
                status_code=404,
                detail="HTML报告文件不存在"
            )

        # 返回文件
        return FileResponse(
            path=result["report"].html_path,
            media_type="text/html",
            filename=f"report_{report_id}.html",
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{report_id}/markdown")
async def get_report_markdown_api(report_id: int = Path(..., gt=0, description="报告ID")):
    """获取Markdown报告"""
    try:
        result = await get_report_content(report_id, "markdown")

        if not result:
            raise HTTPException(status_code=404, detail=f"报告不存在: id={report_id}")

        if not result["exists"]:
            raise HTTPException(
                status_code=404,
                detail=f"Markdown报告文件不存在: {result['report'].markdown_path or '未生成'}"
            )

        # 返回文件内容
        return {
            "success": True,
            "content": result["content"],
            "path": result["report"].markdown_path,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{report_id}/markdown/file")
async def get_report_markdown_file_api(report_id: int = Path(..., gt=0, description="报告ID")):
    """获取Markdown报告文件（直接下载）"""
    try:
        result = await get_report_content(report_id, "markdown")

        if not result:
            raise HTTPException(status_code=404, detail=f"报告不存在: id={report_id}")

        if not result["exists"] or not result["report"].markdown_path:
            raise HTTPException(
                status_code=404,
                detail="Markdown报告文件不存在"
            )

        # 返回文件
        return FileResponse(
            path=result["report"].markdown_path,
            media_type="text/markdown",
            filename=f"report_{report_id}.md",
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/run/{run_id}", response_model=ApiResponse)
async def get_report_by_run_api(run_id: int = Path(..., gt=0, description="执行记录ID")):
    """根据执行记录ID获取报告"""
    try:
        report = await get_report_by_run(run_id)

        if not report:
            return ApiResponse(
                success=False,
                error={"code": "not_found", "message": f"执行记录{run_id}没有关联的报告"}
            )

        return ApiResponse(
            success=True,
            data={"report": _report_to_dict(report)}
        )

    except Exception as e:
        return ApiResponse(
            success=False,
            error={"code": "internal_error", "message": str(e)}
        )


@router.delete("/{report_id}", response_model=ApiResponse)
async def delete_report_api(
    report_id: int = Path(..., gt=0, description="报告ID"),
    delete_files: bool = Query(False, description="是否同时删除报告文件"),
):
    """删除报告"""
    try:
        deleted = await delete_report(report_id, delete_files)

        if not deleted:
            return ApiResponse(
                success=False,
                error={"code": "not_found", "message": f"报告不存在: id={report_id}"}
            )

        return ApiResponse(
            success=True,
            data={
                "deleted": True,
                "report_id": report_id,
                "files_deleted": delete_files,
            }
        )

    except Exception as e:
        return ApiResponse(
            success=False,
            error={"code": "internal_error", "message": str(e)}
        )