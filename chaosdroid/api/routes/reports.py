"""Reports API routes."""
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional

router = APIRouter()


class ReportResponse(BaseModel):
    """报告响应"""
    id: int
    scenario_run_id: int
    markdown_path: Optional[str]
    html_path: Optional[str]
    summary: Optional[dict]


class ApiResponse(BaseModel):
    """统一API响应格式"""
    success: bool
    data: Optional[dict] = None
    error: Optional[dict] = None


@router.get("/{report_id}", response_model=ApiResponse)
async def get_report(report_id: int):
    """获取报告元数据"""
    # TODO: 实现数据库查询
    return ApiResponse(success=True, data={"report": None})


@router.get("/{report_id}/html")
async def get_report_html(report_id: int):
    """获取HTML报告"""
    # TODO: 实现文件读取
    raise HTTPException(status_code=404, detail="Report not found")


@router.get("/{report_id}/markdown")
async def get_report_markdown(report_id: int):
    """获取Markdown报告"""
    # TODO: 实现文件读取
    raise HTTPException(status_code=404, detail="Report not found")