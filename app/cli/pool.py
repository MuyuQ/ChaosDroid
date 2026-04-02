"""
设备池管理 CLI 命令模块。

提供设备池的创建、列表、查看等功能。
"""
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from app.models import get_session_context
from app.scheduling import PoolManager
from app.scheduling.enums import DevicePoolPurpose

# 创建 Typer 应用
pool_app = typer.Typer(
    name="pool",
    help="设备池管理命令",
    add_completion=False,
)

console = Console()


@pool_app.command("list")
def list_pools(
    all_pools: bool = typer.Option(
        False, "--all", "-a", help="显示所有设备池（包括禁用的）"
    ),
) -> None:
    """
    列出所有设备池。

    显示设备池名称、用途、预留比例等信息。
    """
    with get_session_context() as session:
        pool_manager = PoolManager(session)
        pools = pool_manager.list_pools(enabled_only=not all_pools)

        if not pools:
            console.print("[yellow]未找到任何设备池[/yellow]")
            return

        # 创建表格
        table = Table(title="设备池列表", show_header=True, header_style="bold cyan")
        table.add_column("ID", style="green")
        table.add_column("名称", style="cyan")
        table.add_column("用途", style="blue")
        table.add_column("预留比例", style="magenta")
        table.add_column("最大并行", style="yellow")
        table.add_column("状态", style="bold")

        for pool in pools:
            status_style = "green" if pool.enabled else "red"
            status_text = "启用" if pool.enabled else "禁用"
            max_parallel = str(pool.max_parallel_jobs) if pool.max_parallel_jobs else "不限制"

            table.add_row(
                str(pool.id),
                pool.name,
                pool.purpose,
                f"{pool.reserved_emergency_ratio:.0%}",
                max_parallel,
                f"[{status_style}]{status_text}[/{status_style}]",
            )

        console.print(table)
        console.print(f"\n[dim]共 {len(pools)} 个设备池[/dim]")


@pool_app.command("create")
def create_pool(
    name: str = typer.Option(..., "--name", "-n", help="设备池名称"),
    purpose: str = typer.Option(..., "--purpose", "-p", help="用途: stable/stress/emergency"),
    reserved_ratio: float = typer.Option(0.2, "--reserved", "-r", help="预留应急比例"),
    max_parallel: Optional[int] = typer.Option(None, "--max-parallel", "-m", help="最大并行任务数"),
) -> None:
    """
    创建设备池。
    """
    # 验证purpose值
    valid_purposes = [p.value for p in DevicePoolPurpose]
    if purpose not in valid_purposes:
        console.print(f"[red]错误: 无效的purpose值 '{purpose}'[/red]")
        console.print(f"[yellow]有效值为: {', '.join(valid_purposes)}[/yellow]")
        raise typer.Exit(code=1)

    try:
        with get_session_context() as session:
            pool_manager = PoolManager(session)
            pool = pool_manager.create_pool(
                name=name,
                purpose=purpose,
                reserved_emergency_ratio=reserved_ratio,
                max_parallel_jobs=max_parallel,
            )
            console.print(f"[green]设备池创建成功[/green]")
            console.print(f"  ID: {pool.id}")
            console.print(f"  名称: {pool.name}")
            console.print(f"  用途: {pool.purpose}")
            console.print(f"  预留比例: {pool.reserved_emergency_ratio:.0%}")

    except Exception as e:
        console.print(f"[red]创建失败: {e}[/red]")
        raise typer.Exit(code=1)


@pool_app.command("show")
def show_pool(
    pool_id: int = typer.Argument(..., help="设备池ID"),
) -> None:
    """
    显示设备池详情。
    """
    with get_session_context() as session:
        pool_manager = PoolManager(session)
        pool = pool_manager.get_pool(pool_id)

        if not pool:
            console.print(f"[red]错误: 设备池 {pool_id} 不存在[/red]")
            raise typer.Exit(code=1)

        # 获取容量信息
        capacity = pool_manager.get_available_capacity(pool)

        # 显示详情
        console.print(Panel(f"[bold cyan]设备池: {pool.name}[/bold cyan]", expand=False))
        console.print(f"\n[bold]基本信息[/bold]")
        console.print(f"  ID: {pool.id}")
        console.print(f"  名称: {pool.name}")
        console.print(f"  用途: {pool.purpose}")
        console.print(f"  状态: {'[green]启用[/green]' if pool.enabled else '[red]禁用[/red]'}")

        console.print(f"\n[bold]配置信息[/bold]")
        console.print(f"  预留应急比例: {pool.reserved_emergency_ratio:.0%}")
        console.print(f"  最大并行任务数: {pool.max_parallel_jobs or '不限制'}")

        console.print(f"\n[bold]容量信息[/bold]")
        console.print(f"  可用容量: {capacity}")


@pool_app.command("update")
def update_pool(
    pool_id: int = typer.Argument(..., help="设备池ID"),
    name: Optional[str] = typer.Option(None, "--name", "-n", help="新名称"),
    purpose: Optional[str] = typer.Option(None, "--purpose", "-p", help="新用途"),
    reserved_ratio: Optional[float] = typer.Option(None, "--reserved", "-r", help="新预留比例"),
    max_parallel: Optional[int] = typer.Option(None, "--max-parallel", "-m", help="新最大并行数"),
    enable: Optional[bool] = typer.Option(None, "--enable/--disable", help="启用/禁用"),
) -> None:
    """
    更新设备池配置。
    """
    # 验证purpose值
    if purpose:
        valid_purposes = [p.value for p in DevicePoolPurpose]
        if purpose not in valid_purposes:
            console.print(f"[red]错误: 无效的purpose值 '{purpose}'[/red]")
            console.print(f"[yellow]有效值为: {', '.join(valid_purposes)}[/yellow]")
            raise typer.Exit(code=1)

    try:
        with get_session_context() as session:
            pool_manager = PoolManager(session)
            pool = pool_manager.update_pool(
                pool_id=pool_id,
                name=name,
                purpose=purpose,
                reserved_emergency_ratio=reserved_ratio,
                max_parallel_jobs=max_parallel,
                enabled=enable,
            )

            if not pool:
                console.print(f"[red]错误: 设备池 {pool_id} 不存在[/red]")
                raise typer.Exit(code=1)

            console.print(f"[green]设备池更新成功[/green]")
            console.print(f"  ID: {pool.id}")
            console.print(f"  名称: {pool.name}")
            console.print(f"  用途: {pool.purpose}")

    except ValueError as e:
        console.print(f"[red]验证错误: {e}[/red]")
        raise typer.Exit(code=1)
    except Exception as e:
        console.print(f"[red]更新失败: {e}[/red]")
        raise typer.Exit(code=1)


@pool_app.command("delete")
def delete_pool(
    pool_id: int = typer.Argument(..., help="设备池ID"),
    force: bool = typer.Option(False, "--force", "-f", help="强制删除"),
) -> None:
    """
    删除设备池。
    """
    if not force:
        console.print(f"[yellow]警告: 即将删除设备池 {pool_id}[/yellow]")
        confirm = typer.confirm("确定要删除吗？")
        if not confirm:
            console.print("[yellow]已取消[/yellow]")
            return

    try:
        with get_session_context() as session:
            pool_manager = PoolManager(session)
            deleted = pool_manager.delete_pool(pool_id)

            if not deleted:
                console.print(f"[red]错误: 设备池 {pool_id} 不存在[/red]")
                raise typer.Exit(code=1)

            console.print(f"[green]设备池 {pool_id} 已删除[/green]")

    except Exception as e:
        console.print(f"[red]删除失败: {e}[/red]")
        raise typer.Exit(code=1)