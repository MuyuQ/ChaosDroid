"""CLI入口点。"""

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from app.diagnosis.models import init_db
from app.diagnosis.services import IngestService, ParseService, DiagnoseService, ReportService, SimilarCaseService

app = typer.Typer(name="chaosdroid-diagnosis", help="Android 故障诊断工作台")
console = Console()


@app.callback()
def init():
    """初始化数据库。"""
    init_db()


@app.command()
def ingest(
    path: str,
    device_serial: str | None = None,
    test_type: str | None = None,
    build_fingerprint: str | None = None,
):
    """
    导入日志。

    Args:
        path: 日志路径（目录或文件）
        device_serial: 设备序列号
        test_type: 测试类型
        build_fingerprint: 构建指纹
    """
    service = IngestService()
    metadata = {
        "device_serial": device_serial,
        "test_type": test_type,
        "build_fingerprint": build_fingerprint,
    }
    # 过滤None值
    metadata = {k: v for k, v in metadata.items() if v is not None}

    run_id = service.ingest_path(path, metadata)
    console.print(f"[green]成功导入日志[/green]")
    console.print(f"任务ID: [cyan]{run_id}[/cyan]")

    # 显示导入的文件
    artifacts = service.get_artifacts(run_id)
    table = Table(title="导入文件列表")
    table.add_column("文件名")
    table.add_column("来源类型")
    table.add_column("大小")

    for artifact in artifacts:
        table.add_row(
            artifact.file_name,
            artifact.source_type.value,
            f"{artifact.size} bytes" if artifact.size else "N/A",
        )

    console.print(table)


@app.command()
def runs(
    limit: int = 20,
):
    """显示任务列表。"""
    service = IngestService()
    runs = service.list_runs(limit=limit)

    table = Table(title="任务列表")
    table.add_column("任务ID")
    table.add_column("设备")
    table.add_column("状态")
    table.add_column("开始时间")

    for run in runs:
        table.add_row(
            run.run_id,
            run.device_serial or "N/A",
            run.status.value,
            run.started_at.strftime("%Y-%m-%d %H:%M:%S"),
        )

    console.print(table)


@app.command()
def parse(run_id: str):
    """
    解析指定任务的日志。

    Args:
        run_id: 任务ID
    """
    from app.diagnosis.exceptions import NotFoundError, ParseError

    service = ParseService()
    try:
        events = service.parse_run(run_id)
    except NotFoundError:
        console.print(f"[red]找不到任务 {run_id}[/red]")
        console.print("[yellow]事件数量: 0[/yellow]")
        return
    except ParseError as e:
        console.print(f"[red]解析失败: {e.message}[/red]")
        return

    console.print(f"[green]解析完成[/green]")
    console.print(f"任务ID: [cyan]{run_id}[/cyan]")
    console.print(f"事件数量: [yellow]{len(events)}[/yellow]")

    # 显示事件摘要
    event_codes = {}
    for event in events:
        code = event.normalized_code
        event_codes[code] = event_codes.get(code, 0) + 1

    table = Table(title="事件摘要")
    table.add_column("标准化代码")
    table.add_column("数量")
    table.add_column("阶段")

    for code, count in sorted(event_codes.items(), key=lambda x: -x[1]):
        # 找到对应事件获取阶段
        stage = next((e.stage.value for e in events if e.normalized_code == code), "N/A")
        table.add_row(code, str(count), stage)

    console.print(table)


@app.command()
def diagnose(run_id: str):
    """
    执行完整诊断流程。

    Args:
        run_id: 任务ID
    """
    from app.diagnosis.exceptions import NotFoundError, DiagnosisError

    service = DiagnoseService()
    try:
        result = service.diagnose(run_id)
    except NotFoundError:
        console.print(f"[red]找不到任务 {run_id}[/red]")
        return
    except DiagnosisError as e:
        console.print(f"[red]诊断失败: {e.message}[/red]")
        return

    if not result:
        console.print(f"[red]诊断失败：找不到任务 {run_id}[/red]")
        return

    # 显示诊断结果
    console.print(Panel.fit(
        f"[bold]诊断结果[/bold]\n"
        f"任务ID: [cyan]{result.run_id}[/cyan]\n"
        f"阶段: [yellow]{result.stage.value}[/yellow]\n"
        f"分类: [magenta]{result.category}[/magenta]\n"
        f"根因: [red]{result.root_cause}[/red]\n"
        f"置信度: [green]{result.confidence:.0%}[/green]\n"
        f"状态: [bold]{result.result_status.value}[/bold]",
        title="ChaosDroid 诊断报告",
    ))

    if result.next_action:
        console.print(f"\n[bold]建议动作:[/bold] {result.next_action}")

    if result.key_evidence:
        console.print(f"\n[bold]关键证据:[/bold]")
        for i, evidence in enumerate(result.key_evidence, 1):
            console.print(f"  {i}. {evidence}")


@app.command()
def run(
    path: str,
    device_serial: str | None = None,
    test_type: str | None = None,
):
    """
    一键执行：导入 -> 解析 -> 诊断。

    Args:
        path: 日志路径
        device_serial: 设备序列号
        test_type: 测试类型
    """
    # 导入
    ingest_service = IngestService()
    metadata = {"device_serial": device_serial, "test_type": test_type}
    metadata = {k: v for k, v in metadata.items() if v is not None}
    run_id = ingest_service.ingest_path(path, metadata)
    console.print(f"[green]✓[/green] 导入完成: {run_id}")

    # 解析
    parse_service = ParseService()
    events = parse_service.parse_run(run_id)
    console.print(f"[green]✓[/green] 解析完成: {len(events)} 个事件")

    # 诊断
    diagnose_service = DiagnoseService()
    result = diagnose_service.diagnose(run_id)
    console.print(f"[green]✓[/green] 诊断完成")

    # 显示结果
    if result:
        console.print(Panel.fit(
            f"[bold]分类:[/bold] {result.category}\n"
            f"[bold]根因:[/bold] {result.root_cause}\n"
            f"[bold]置信度:[/bold] {result.confidence:.0%}\n"
            f"[bold]状态:[/bold] {result.result_status.value}",
            title="诊断结果",
        ))


# 创建子命令组
report_app = typer.Typer(name="report", help="报告管理")
app.add_typer(report_app, name="report")

cases_app = typer.Typer(name="cases", help="案例管理")
app.add_typer(cases_app, name="cases")


@report_app.command("export")
def report_export(
    run_id: str,
    format: str = typer.Option("markdown", "--format", "-f", help="输出格式: markdown 或 html"),
    output: str | None = typer.Option(None, "--output", "-o", help="输出文件路径"),
):
    """
    导出诊断报告。

    Args:
        run_id: 任务ID
        format: 输出格式 (markdown/html)
        output: 输出文件路径
    """
    service = ReportService()

    if output is None:
        output = f"report_{run_id}.{format}"

    if format == "html":
        service.export_html(run_id, output)
    else:
        service.export_markdown(run_id, output)

    console.print(f"[green]报告已导出:[/green] {output}")


@cases_app.command("rebuild-index")
def cases_rebuild_index():
    """重建相似案例索引。"""
    service = SimilarCaseService()
    count = service.rebuild_index()
    console.print(f"[green]重建完成:[/green] 已索引 {count} 个案例")


@app.command()
def web(
    host: str = "127.0.0.1",
    port: int = 8000,
):
    """
    启动Web服务。

    Args:
        host: 监听地址
        port: 监听端口
    """
    import uvicorn
    from app.diagnosis.web.app import create_app

    app = create_app()
    console.print(f"[green]启动Web服务:[/green] http://{host}:{port}")
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    app()