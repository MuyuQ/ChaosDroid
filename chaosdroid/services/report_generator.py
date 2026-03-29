"""报告生成服务."""
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import dataclass, field

from chaosdroid.config.settings import get_settings
from chaosdroid.validators.base import JudgmentResult


@dataclass
class ReportData:
    """报告数据"""
    scenario_name: str
    device_serial: str
    inject_stage: str
    fault_type: str
    inject_summary: Dict[str, Any] = field(default_factory=dict)
    validation_summary: Dict[str, Any] = field(default_factory=dict)
    recovery_summary: Dict[str, Any] = field(default_factory=dict)
    judgment: Optional[JudgmentResult] = None
    evidence: Dict[str, Any] = field(default_factory=dict)
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    duration_sec: float = 0.0


class ReportGenerator:
    """报告生成器"""

    def __init__(self, scenario_run_id: int):
        self.scenario_run_id = scenario_run_id
        self.settings = get_settings()
        self.reports_dir = self.settings.get_reports_dir()
        self.reports_dir.mkdir(parents=True, exist_ok=True)

    def get_report_path(self, format: str) -> Path:
        """获取报告路径"""
        return self.reports_dir / f"report_{self.scenario_run_id}.{format}"

    def generate_markdown(self, data: ReportData) -> str:
        """生成Markdown报告"""
        lines = [
            f"# ChaosDroid 测试报告",
            f"",
            f"**场景名称:** {data.scenario_name}",
            f"**设备序列号:** {data.device_serial}",
            f"**注入阶段:** {data.inject_stage}",
            f"**故障类型:** {data.fault_type}",
            f"",
            f"## 执行时间",
            f"",
            f"- **开始时间:** {data.started_at and data.started_at.isoformat() or 'N/A'}",
            f"- **结束时间:** {data.finished_at and data.finished_at.isoformat() or 'N/A'}",
            f"- **执行时长:** {data.duration_sec:.2f}秒",
            f"",
            f"## 注入动作摘要",
            f"",
        ]

        if data.inject_summary:
            lines.extend(self._format_summary(data.inject_summary))
        else:
            lines.append("无注入记录")

        lines.extend([
            f"",
            f"## 验证动作摘要",
            f"",
        ])

        if data.validation_summary:
            lines.extend(self._format_summary(data.validation_summary))
        else:
            lines.append("无验证记录")

        lines.extend([
            f"",
            f"## 恢复动作摘要",
            f"",
        ])

        if data.recovery_summary:
            lines.extend(self._format_summary(data.recovery_summary))
        else:
            lines.append("无恢复记录")

        # 最终结论
        lines.extend([
            f"",
            f"## 最终结论",
            f"",
        ])

        if data.judgment:
            lines.extend([
                f"| 项目 | 结果 |",
                f"|------|------|",
                f"| 故障注入 | {data.judgment.fault_injected and '成功' or '失败'} |",
                f"| 故障观测 | {data.judgment.fault_observed and '已观测' or '未观测'} |",
                f"| 验证判定 | {data.judgment.validation_passed and '通过' or '失败'} |",
                f"| 恢复结果 | {data.judgment.recovery_passed and '成功' or '失败'} |",
                f"| **最终状态** | **{data.judgment.final_status.upper()}** |",
                f"| 风险等级 | {data.judgment.risk_level} |",
                f"| 需人工介入 | {data.judgment.manual_action_required and '是' or '否'} |",
                f"",
                f"**结论说明:** {data.judgment.message}",
            ])

        # 关键证据
        lines.extend([
            f"",
            f"## 关键证据",
            f"",
        ])

        if data.evidence:
            lines.extend(self._format_evidence(data.evidence))
        else:
            lines.append("无关键证据")

        # 建议动作
        lines.extend([
            f"",
            f"## 建议动作",
            f"",
        ])

        if data.judgment and data.judgment.manual_action_required:
            lines.extend([
                f"- 检查设备状态并尝试手动恢复",
                f"- 查看详细日志确认问题根因",
                f"- 联系相关责任人处理",
            ])
        elif data.judgment and data.judgment.final_status == "passed":
            lines.extend([
                f"- 测试通过，无需额外处理",
                f"- 可继续执行下一测试场景",
            ])
        else:
            lines.extend([
                f"- 检查注入和恢复步骤的详细日志",
                f"- 确认故障是否正确注入",
                f"- 分析验证失败的具体原因",
            ])

        return "\n".join(lines)

    def generate_html(self, markdown_content: str) -> str:
        """生成HTML报告（简单转换）"""
        # 简单的HTML包装，实际可使用markdown库
        html_template = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ChaosDroid 测试报告</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
            background: #f5f5f5;
        }
        .report-container {
            background: white;
            padding: 30px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        h1 {
            color: #333;
            border-bottom: 2px solid #4CAF50;
            padding-bottom: 10px;
        }
        h2 {
            color: #444;
            margin-top: 20px;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            margin: 10px 0;
        }
        th, td {
            border: 1px solid #ddd;
            padding: 8px;
            text-align: left;
        }
        th {
            background: #f9f9f9;
        }
        .status-passed { color: #4CAF50; font-weight: bold; }
        .status-failed { color: #f44336; font-weight: bold; }
        .status-partial { color: #ff9800; font-weight: bold; }
        ul { line-height: 1.6; }
        code { background: #f4f4f4; padding: 2px 6px; border-radius: 3px; }
    </style>
</head>
<body>
    <div class="report-container">
        <!-- Markdown content converted to HTML -->
        {content}
    </div>
</body>
</html>"""
        # 简单转换
        content = self._markdown_to_html(markdown_content)
        return html_template.format(content=content)

    def _markdown_to_html(self, md: str) -> str:
        """简单Markdown到HTML转换"""
        html = md

        # 标题
        html = html.replace("# ChaosDroid 测试报告", "<h1>ChaosDroid 测试报告</h1>")
        for i in range(2, 7):
            pattern = f"{'#' * i} "
            replacement = f"<h{i}>"
            html = html.replace(pattern, replacement)

        # 表格
        lines = html.split("\n")
        result_lines = []
        in_table = False
        for line in lines:
            if line.startswith("|") and "|" in line:
                if not in_table:
                    result_lines.append("<table>")
                    in_table = True
                cells = [c.strip() for c in line.split("|")[1:-1]]
                if all(c.replace("-", "") == "" for c in cells):
                    # 分隔行，跳过
                    continue
                row = "<tr>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>"
                result_lines.append(row)
            else:
                if in_table:
                    result_lines.append("</table>")
                    in_table = False
                # 处理粗体
                line = line.replace("**", "<strong>", 1).replace("**", "</strong>", 1)
                # 处理列表
                if line.startswith("- "):
                    line = "<li>" + line[2:] + "</li>"
                result_lines.append(line)
        if in_table:
            result_lines.append("</table>")

        return "\n".join(result_lines)

    def _format_summary(self, summary: Dict[str, Any]) -> list:
        """格式化摘要"""
        lines = []
        for key, value in summary.items():
            if isinstance(value, dict):
                lines.append(f"### {key}")
                for k, v in value.items():
                    lines.append(f"- {k}: {v}")
            else:
                lines.append(f"- {key}: {value}")
        return lines

    def _format_evidence(self, evidence: Dict[str, Any]) -> list:
        """格式化证据"""
        lines = []
        for key, value in evidence.items():
            if isinstance(value, str) and len(value) > 200:
                value = value[:200] + "..."
            lines.append(f"- **{key}:** `{value}`")
        return lines

    def save_reports(self, data: ReportData) -> Dict[str, str]:
        """保存报告"""
        markdown_content = self.generate_markdown(data)
        html_content = self.generate_html(markdown_content)

        md_path = self.get_report_path("md")
        html_path = self.get_report_path("html")

        md_path.write_text(markdown_content, encoding="utf-8")
        html_path.write_text(html_content, encoding="utf-8")

        return {
            "markdown_path": str(md_path),
            "html_path": str(html_path)
        }

    def generate_summary_json(self, data: ReportData) -> str:
        """生成摘要JSON"""
        summary = {
            "scenario_name": data.scenario_name,
            "device_serial": data.device_serial,
            "fault_type": data.fault_type,
            "inject_stage": data.inject_stage,
            "started_at": data.started_at and data.started_at.isoformat(),
            "finished_at": data.finished_at and data.finished_at.isoformat(),
            "duration_sec": data.duration_sec,
            "judgment": data.judgment and {
                "final_status": data.judgment.final_status,
                "fault_injected": data.judgment.fault_injected,
                "validation_passed": data.judgment.validation_passed,
                "recovery_passed": data.judgment.recovery_passed,
                "risk_level": data.judgment.risk_level,
                "manual_action_required": data.judgment.manual_action_required
            },
            "inject_summary": data.inject_summary,
            "validation_summary": data.validation_summary,
            "recovery_summary": data.recovery_summary
        }
        return json.dumps(summary, indent=2, ensure_ascii=False)