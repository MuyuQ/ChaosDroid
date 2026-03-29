"""
执行管理 CLI 命令模块。

提供场景执行的创建、查看、取消等功能。
"""
from typing import Optional
from enum import Enum
from datetime import datetime

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

# 创建 Typer 应用
run_app = typer.Typer(
    name="run",
    help="场景执行管理命令",
    add_completion=False,
)

console = Console()


class RunStatus(str, Enum):
    """执行状态枚举。"""
    QUEUED = "queued"
    PREPARING = "preparing"
    INJECTING = "injecting"
    VALIDATING = "validating"
    RECOVERING = "recovering"
    PASSED = "passed"
    FAILED = "failed"
    PARTIAL = "partial"


class ExecutorMode(str, Enum):
    """执行模式枚举。"""
    REAL = "real"
    MOCK = "mock"


@run_app.command("execute")
def execute_scenario(
    scenario_id: int = typer.Argument(..., help="场景模板ID"),
    device: str = typer.Option(..., "--device", "-d", help="设备序列号"),
    mode: ExecutorMode = typer.Option(
        ExecutorMode.MOCK, "--mode", "-m", help="执行模式 (real/mock)"
    ),
    wait: bool = typer.Option(
        False, "--wait", "-w", help="等待执行完成"
    ),
    timeout: int = typer.Option(
        300, "--timeout", help="超时时间（秒）"
    ),
) -> None:
    """
    执行场景模板。

    在指定设备上运行故障注入场景。
    """
    console.print(Panel(f"[bold cyan]执行场景模板[/bold cyan]", expand=False))
    console.print(f"[green]场景ID:[/green] {scenario_id}")
    console.print(f"[green]设备序列号:[/green] {device}")
    console.print(f"[green]执行模式:[/green] {mode.value}")
    console.print(f"[green]超时时间:[/green] {timeout}秒")

    # 检查设备状态
    if not _check_device_online(device, mode.value):
        console.print(f"[red]错误: 设备 {device} 不在线[/red]")
        raise typer.Exit(code=1)

    # 创建执行记录
    run_id = _create_run_record(scenario_id, device, mode.value)
    console.print(f"\n[dim]执行记录ID: {run_id}[/dim]")

    if wait:
        # 等待执行完成
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("正在执行场景...", total=None)

            result = _execute_and_wait(run_id, timeout)

            progress.remove_task(task)

        # 显示执行结果
        _display_run_result(result)
    else:
        # 异步执行，返回执行ID
        _start_async_execution(run_id)
        console.print(f"\n[bold green]✓ 场景执行已启动[/bold green]")
        console.print(f"[dim]使用 'chaosdroid run show {run_id}' 查看执行状态[/dim]")


@run_app.command("list")
def list_runs(
    status: Optional[RunStatus] = typer.Option(
        None, "--status", "-s", help="按状态筛选"
    ),
    scenario_id: Optional[int] = typer.Option(
        None, "--scenario", "-t", help="按场景ID筛选"
    ),
    device: Optional[str] = typer.Option(
        None, "--device", "-d", help="按设备筛选"
    ),
    limit: int = typer.Option(
        10, "--limit", "-l", help="显示数量限制"
    ),
) -> None:
    """
    列出执行记录。

    支持按状态、场景ID、设备进行筛选。
    """
    # TODO: 从数据库查询执行记录
    runs = _get_mock_runs(status, scenario_id, device, limit)

    if not runs:
        console.print("[yellow]未找到匹配的执行记录[/yellow]")
        return

    # 创建表格
    table = Table(title="执行记录列表", show_header=True, header_style="bold cyan")
    table.add_column("ID", style="dim", width=6)
    table.add_column("场景", style="green")
    table.add_column("设备", style="blue")
    table.add_column("状态", style="bold")
    table.add_column("开始时间", style="magenta")
    table.add_column("结束时间", style="magenta")
    table.add_column("结论", style="yellow")

    for run in runs:
        status_style = _get_status_style(run["status"])
        table.add_row(
            str(run["id"]),
            run["scenario_name"],
            run["device_serial"],
            f"[{status_style}]{run['status']}[/{status_style}]",
            run["started_at"],
            run["finished_at"] or "-",
            run["conclusion"] or "-",
        )

    console.print(table)
    console.print(f"\n[dim]共 {len(runs)} 条执行记录[/dim]")


@run_app.command("show")
def show_run(
    run_id: int = typer.Argument(..., help="执行记录ID"),
    steps: bool = typer.Option(
        False, "--steps", help="显示执行步骤详情"
    ),
) -> None:
    """
    显示执行记录详情。

    包括执行状态、步骤、结果等详细信息。
    """
    # TODO: 从数据库查询执行详情
    run = _get_run_by_id(run_id)

    if not run:
        console.print(f"[red]错误: 未找到ID为 {run_id} 的执行记录[/red]")
        raise typer.Exit(code=1)

    # 显示基本信息
    console.print(Panel(f"[bold cyan]执行记录详情[/bold cyan]", expand=False))
    console.print(f"\n[bold]基本信息[/bold]")
    console.print(f"  ID: {run['id']}")
    console.print(f"  场景: {run['scenario_name']} (ID: {run['scenario_template_id']})")
    console.print(f"  设备: {run['device_serial']}")
    console.print(f"  注入阶段: {run['inject_stage']}")

    # 显示状态
    status_style = _get_status_style(run["status"])
    console.print(f"\n[bold]执行状态[/bold]")
    console.print(f"  状态: [{status_style}]{run['status']}[/{status_style}]")
    console.print(f"  开始时间: {run['started_at']}")
    console.print(f"  结束时间: {run['finished_at'] or '进行中'}")

    # 显示执行结果
    if run["result_summary"]:
        console.print(f"\n[bold]执行结果[/bold]")
        result = run["result_summary"]
        console.print(f"  故障注入: {'成功' if result.get('fault_injected') else '失败'}")
        console.print(f"  故障观测: {'是' if result.get('fault_observed') else '否'}")
        console.print(f"  验证通过: {'是' if result.get('validation_passed') else '否'}")
        console.print(f"  恢复成功: {'是' if result.get('recovery_passed') else '否'}")
        console.print(f"  风险等级: {result.get('risk_level', 'N/A')}")

    # 显示步骤详情
    if steps and run.get("step_records"):
        console.print(f"\n[bold]执行步骤[/bold]")
        step_table = Table(show_header=True, header_style="bold cyan")
        step_table.add_column("顺序", width=6)
        step_table.add_column("类型")
        step_table.add_column("状态")
        step_table.add_column("开始时间")
        step_table.add_column("结束时间")

        for step in run["step_records"]:
            step_status_style = _get_status_style(step["status"])
            step_table.add_row(
                str(step["step_order"]),
                step["step_type"],
                f"[{step_status_style}]{step['status']}[/{step_status_style}]",
                step["started_at"],
                step["finished_at"] or "-",
            )

        console.print(step_table)


@run_app.command("cancel")
def cancel_run(
    run_id: int = typer.Argument(..., help="执行记录ID"),
    force: bool = typer.Option(
        False, "--force", "-f", help="强制取消，不询问确认"
    ),
) -> None:
    """
    取消正在执行的记录。

    仅能取消状态为 queued 或 preparing 的执行。
    """
    # TODO: 从数据库查询执行状态
    run = _get_run_by_id(run_id)

    if not run:
        console.print(f"[red]错误: 未找到ID为 {run_id} 的执行记录[/red]")
        raise typer.Exit(code=1)

    # 检查是否可取消
    cancellable_states = ["queued", "preparing"]
    if run["status"] not in cancellable_states:
        console.print(f"[red]错误: 执行状态为 '{run['status']}'，无法取消[/red]")
        console.print(f"[dim]仅状态为 {cancellable_states} 的执行可取消[/dim]")
        raise typer.Exit(code=1)

    if not force:
        confirm = typer.confirm(
            f"确定要取消执行记录 {run_id} 吗？",
            default=False,
        )
        if not confirm:
            console.print("[yellow]操作已取消[/yellow]")
            return

    # TODO: 实际取消逻辑
    success = _cancel_run_in_db(run_id)

    if success:
        console.print(f"[bold green]✓ 执行记录 {run_id} 已取消[/bold green]")
    else:
        console.print(f"[red]错误: 取消执行记录 {run_id} 失败[/red]")
        raise typer.Exit(code=1)


# ==================== 辅助函数 ====================

def _get_status_style(status: str) -> str:
    """获取状态对应的样式。"""
    status_styles = {
        "queued": "dim",
        "preparing": "yellow",
        "injecting": "orange1",
        "validating": "blue",
        "recovering": "magenta",
        "passed": "green",
        "failed": "red",
        "partial": "yellow",
    }
    return status_styles.get(status, "white")


def _display_run_result(result: dict) -> None:
    """显示执行结果。"""
    console.print(f"\n[bold]执行结果[/bold]")

    status_style = _get_status_style(result["status"])
    console.print(f"  最终状态: [{status_style}]{result['status']}[/{status_style}]")

    if result.get("conclusion"):
        conclusion_style = "green" if result["conclusion"] == "passed" else "red"
        console.print(f"  结论: [{conclusion_style}]{result['conclusion']}[/{conclusion_style}]")

    console.print(f"  总耗时: {result.get('duration', 'N/A')}秒")

    if result.get("error"):
        console.print(f"  [red]错误: {result['error']}[/red]")


# ==================== 模拟数据函数 ====================

def _check_device_online(device: str, mode: str) -> bool:
    """检查设备是否在线。"""
    # TODO: 实际设备检查逻辑
    console.print("[dim]正在检查设备状态...[/dim]")
    return True


def _create_run_record(scenario_id: int, device: str, mode: str) -> int:
    """创建执行记录。"""
    # TODO: 实际数据库操作
    console.print("[dim]正在创建执行记录...[/dim]")
    return 1


def _start_async_execution(run_id: int) -> None:
    """启动异步执行。"""
    # TODO: 实际异步执行逻辑
    pass


def _execute_and_wait(run_id: int, timeout: int) -> dict:
    """同步执行并等待完成。"""
    # TODO: 实际执行逻辑
    import time
    time.sleep(0.5)  # 模拟执行时间

    return {
        "run_id": run_id,
        "status": "passed",
        "conclusion": "passed",
        "duration": 45,
        "error": None,
    }


def _get_mock_runs(
    status: Optional[RunStatus],
    scenario_id: Optional[int],
    device: Optional[str],
    limit: int,
) -> list[dict]:
    """获取模拟执行记录列表。"""
    mock_data = [
        {
            "id": 1,
            "scenario_name": "存储压力测试",
            "device_serial": "emulator-5554",
            "status": "passed",
            "started_at": "2026-03-30 10:00:00",
            "finished_at": "2026-03-30 10:05:30",
            "conclusion": "passed",
        },
        {
            "id": 2,
            "scenario_name": "低电量阻断测试",
            "device_serial": "emulator-5554",
            "status": "failed",
            "started_at": "2026-03-30 11:00:00",
            "finished_at": "2026-03-30 11:03:20",
            "conclusion": "failed",
        },
        {
            "id": 3,
            "scenario_name": "Monkey稳定性测试",
            "device_serial": "emulator-5556",
            "status": "injecting",
            "started_at": "2026-03-30 12:00:00",
            "finished_at": None,
            "conclusion": None,
        },
        {
            "id": 4,
            "scenario_name": "网络波动测试",
            "device_serial": "real-device-001",
            "status": "partial",
            "started_at": "2026-03-29 14:00:00",
            "finished_at": "2026-03-29 14:10:00",
            "conclusion": "partial",
        },
    ]

    # 应用筛选
    result = mock_data
    if status:
        result = [r for r in result if r["status"] == status.value]
    if scenario_id:
        result = [r for r in result if r["id"] == scenario_id]  # 简化模拟
    if device:
        result = [r for r in result if r["device_serial"] == device]

    return result[:limit]


def _get_run_by_id(run_id: int) -> Optional[dict]:
    """根据ID获取执行记录详情。"""
    # 模拟不存在的记录
    if run_id > 100:
        return None

    return {
        "id": run_id,
        "scenario_template_id": 1,
        "scenario_name": "存储压力测试",
        "device_serial": "emulator-5554",
        "status": "passed",
        "started_at": "2026-03-30 10:00:00",
        "finished_at": "2026-03-30 10:05:30",
        "inject_stage": "upgrading",
        "result_summary": {
            "fault_injected": True,
            "fault_observed": True,
            "validation_passed": True,
            "recovery_passed": True,
            "risk_level": "low",
            "manual_action_required": False,
        },
        "step_records": [
            {
                "step_order": 1,
                "step_type": "precheck",
                "status": "passed",
                "started_at": "2026-03-30 10:00:00",
                "finished_at": "2026-03-30 10:00:30",
            },
            {
                "step_order": 2,
                "step_type": "inject",
                "status": "passed",
                "started_at": "2026-03-30 10:00:30",
                "finished_at": "2026-03-30 10:02:00",
            },
            {
                "step_order": 3,
                "step_type": "validate",
                "status": "passed",
                "started_at": "2026-03-30 10:02:00",
                "finished_at": "2026-03-30 10:04:00",
            },
            {
                "step_order": 4,
                "step_type": "recover",
                "status": "passed",
                "started_at": "2026-03-30 10:04:00",
                "finished_at": "2026-03-30 10:05:30",
            },
        ],
    }


def _cancel_run_in_db(run_id: int) -> bool:
    """取消执行记录。"""
    # TODO: 实际数据库操作
    console.print("[dim]正在取消执行记录...[/dim]")
    return True