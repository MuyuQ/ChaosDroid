"""
Worker CLI 命令模块。

提供后台工作进程管理功能，包括调度器和设备同步。
"""
import asyncio
import signal
from datetime import datetime

import typer
from rich.console import Console
from rich.table import Table
from rich.live import Live

from app.models import get_session_context
from app.scheduling import Scheduler, DeviceSyncService
from app.models.base import RunStatus

# 创建 Typer 应用
worker_app = typer.Typer(
    name="worker",
    help="后台工作进程管理命令",
    add_completion=False,
)

console = Console()


@worker_app.command("run")
def run_worker(
    interval: int = typer.Option(5, "--interval", "-i", help="调度间隔(秒)"),
    sync_interval: int = typer.Option(30, "--sync-interval", "-s", help="设备同步间隔(秒)"),
    once: bool = typer.Option(False, "--once", "-o", help="只执行一次"),
) -> None:
    """
    启动后台工作进程。

    工作进程会定期执行：
    1. 设备状态同步
    2. 任务调度分配
    3. 设备健康检查和隔离
    """
    console.print("[cyan]启动后台工作进程...[/cyan]")
    console.print(f"  调度间隔: {interval}秒")
    console.print(f"  同步间隔: {sync_interval}秒")

    if once:
        console.print("[yellow]模式: 单次执行[/yellow]")
        asyncio.run(_run_once())
    else:
        console.print("[yellow]模式: 持续运行[/yellow]")
        console.print("[dim]按 Ctrl+C 停止[/dim]")
        asyncio.run(_run_loop(interval, sync_interval))


async def _run_once():
    """执行一次调度循环."""
    with get_session_context() as session:
        scheduler = Scheduler(session)
        sync_service = DeviceSyncService(session)

        console.print("\n[bold]执行调度...[/bold]")
        allocated = scheduler.schedule_once()
        console.print(f"[green]分配任务数: {allocated}[/green]")

        console.print("\n[bold]检查设备健康...[/bold]")
        await sync_service.check_and_quarantine()

        console.print("\n[bold]调度统计[/bold]")
        stats = scheduler.get_scheduling_stats()
        console.print(f"  排队任务: {stats['queued_runs']}")
        console.print(f"  已分配任务: {stats['reserved_runs']}")
        console.print(f"  被抢占任务: {stats['preempted_runs']}")
        console.print(f"  空闲设备: {stats['idle_devices']}")

        console.print("\n[green]单次执行完成[/green]")


async def _run_loop(interval: int, sync_interval: int):
    """持续运行调度循环."""
    running = True
    sync_counter = 0

    def stop_handler():
        console.print("\n[yellow]收到停止信号...[/yellow]")
        running = False

    # 注册信号处理
    loop = asyncio.get_event_loop()
    loop.add_signal_handler(signal.SIGINT, stop_handler)
    loop.add_signal_handler(signal.SIGTERM, stop_handler)

    console.print("\n[bold cyan]工作进程已启动[/bold cyan]")

    while running:
        try:
            with get_session_context() as session:
                scheduler = Scheduler(session)
                sync_service = DeviceSyncService(session)

                # 执行调度
                allocated = scheduler.schedule_once()

                # 设备同步（根据间隔）
                if sync_counter >= sync_interval // interval:
                    await sync_service.check_and_quarantine()
                    sync_counter = 0
                else:
                    sync_counter += 1

                # 显示状态
                now = datetime.now().strftime("%H:%M:%S")
                stats = scheduler.get_scheduling_stats()
                console.print(
                    f"[{now}] 调度: {allocated} 分配 | "
                    f"排队: {stats['queued_runs']} | "
                    f"空闲设备: {stats['idle_devices']}"
                )

            await asyncio.sleep(interval)

        except Exception as e:
            console.print(f"[red]调度异常: {e}[/red]")
            await asyncio.sleep(interval)

    console.print("[green]工作进程已停止[/green]")


@worker_app.command("stats")
def show_stats() -> None:
    """
    显示调度统计信息。
    """
    with get_session_context() as session:
        scheduler = Scheduler(session)

        stats = scheduler.get_scheduling_stats()

        console.print("\n[bold]调度统计[/bold]")

        table = Table(show_header=True, header_style="bold cyan")
        table.add_column("指标", style="cyan")
        table.add_column("数值", style="green")

        table.add_row("排队任务", str(stats["queued_runs"]))
        table.add_row("已分配任务", str(stats["reserved_runs"]))
        table.add_row("被抢占任务", str(stats["preempted_runs"]))
        table.add_row("空闲设备", str(stats["idle_devices"]))

        console.print(table)