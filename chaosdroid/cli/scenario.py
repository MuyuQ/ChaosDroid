"""
场景管理 CLI 命令模块。

提供场景模板的创建、查看、启用/禁用、克隆等管理功能。
"""
from typing import Optional
from enum import Enum

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import print as rprint

# 创建 Typer 应用
scenario_app = typer.Typer(
    name="scenario",
    help="场景模板管理命令",
    add_completion=False,
)

console = Console()


class FaultType(str, Enum):
    """故障类型枚举。"""
    STORAGE_PRESSURE = "storage_pressure"
    LOW_BATTERY = "low_battery"
    NETWORK_JITTER = "network_jitter"
    REBOOT_TIMEOUT = "reboot_timeout"
    CPU_IO_STRESS = "cpu_io_stress"
    MONKEY_STABILITY = "monkey_stability"


class TargetType(str, Enum):
    """目标类型枚举。"""
    UPGRADE = "upgrade"
    STABILITY = "stability"
    MONKEY = "monkey"
    RECOVERY = "recovery"


@scenario_app.command("list")
def list_scenarios(
    enabled_only: bool = typer.Option(
        False, "--enabled-only", "-e", help="仅显示启用的场景"
    ),
    fault_type: Optional[FaultType] = typer.Option(
        None, "--fault-type", "-t", help="按故障类型筛选"
    ),
) -> None:
    """
    列出所有场景模板。

    支持按启用状态和故障类型进行筛选。
    """
    # TODO: 从数据库查询场景列表
    # 当前返回模拟数据
    scenarios = _get_mock_scenarios(enabled_only, fault_type)

    if not scenarios:
        console.print("[yellow]未找到匹配的场景模板[/yellow]")
        return

    # 创建表格显示场景列表
    table = Table(title="场景模板列表", show_header=True, header_style="bold cyan")
    table.add_column("ID", style="dim", width=6)
    table.add_column("名称", style="green")
    table.add_column("故障类型", style="yellow")
    table.add_column("目标类型", style="blue")
    table.add_column("注入阶段", style="magenta")
    table.add_column("状态", style="bold")
    table.add_column("描述", width=30)

    for scenario in scenarios:
        status_style = "green" if scenario["enabled"] else "red"
        status_text = "启用" if scenario["enabled"] else "禁用"
        table.add_row(
            str(scenario["id"]),
            scenario["name"],
            scenario["fault_type"],
            scenario["target_type"],
            scenario["inject_stage"],
            f"[{status_style}]{status_text}[/{status_style}]",
            scenario["description"][:30] + "..." if len(scenario["description"]) > 30 else scenario["description"],
        )

    console.print(table)
    console.print(f"\n[dim]共 {len(scenarios)} 个场景模板[/dim]")


@scenario_app.command("create")
def create_scenario(
    name: str = typer.Option(..., "--name", "-n", help="场景名称"),
    fault_type: FaultType = typer.Option(..., "--fault-type", "-t", help="故障类型"),
    description: Optional[str] = typer.Option(
        None, "--description", "-d", help="场景描述"
    ),
    target_type: TargetType = typer.Option(
        TargetType.STABILITY, "--target-type", help="目标类型"
    ),
    inject_stage: str = typer.Option(
        "post_boot", "--inject-stage", "-i", help="注入阶段"
    ),
    executor_mode: str = typer.Option(
        "mock", "--mode", "-m", help="执行模式 (real/mock)"
    ),
) -> None:
    """
    创建新的场景模板。

    需要指定场景名称和故障类型，其他参数可选。
    """
    console.print(Panel(f"[bold cyan]创建场景模板[/bold cyan]", expand=False))

    # 显示创建参数
    console.print(f"[green]场景名称:[/green] {name}")
    console.print(f"[green]故障类型:[/green] {fault_type.value}")
    console.print(f"[green]目标类型:[/green] {target_type.value}")
    console.print(f"[green]注入阶段:[/green] {inject_stage}")
    console.print(f"[green]执行模式:[/green] {executor_mode}")
    if description:
        console.print(f"[green]描述:[/green] {description}")

    # TODO: 实际创建逻辑
    # 1. 创建关联的 FaultProfile（如果不存在默认配置）
    # 2. 创建关联的 ValidationProfile（默认配置）
    # 3. 创建关联的 RecoveryProfile（默认配置）
    # 4. 创建 ScenarioTemplate 记录

    # 模拟创建结果
    scenario_id = _create_scenario_in_db(
        name=name,
        fault_type=fault_type.value,
        description=description or "",
        target_type=target_type.value,
        inject_stage=inject_stage,
        executor_mode=executor_mode,
    )

    console.print(f"\n[bold green]✓ 场景模板创建成功！[/bold green]")
    console.print(f"[dim]场景ID: {scenario_id}[/dim]")


@scenario_app.command("show")
def show_scenario(
    scenario_id: int = typer.Argument(..., help="场景ID"),
) -> None:
    """
    显示场景模板详情。

    包括关联的故障配置、验证配置和恢复配置。
    """
    # TODO: 从数据库查询场景详情
    scenario = _get_scenario_by_id(scenario_id)

    if not scenario:
        console.print(f"[red]错误: 未找到ID为 {scenario_id} 的场景模板[/red]")
        raise typer.Exit(code=1)

    # 显示场景详情
    console.print(Panel(f"[bold cyan]场景模板详情[/bold cyan]", expand=False))
    console.print(f"\n[bold]基本信息[/bold]")
    console.print(f"  ID: {scenario['id']}")
    console.print(f"  名称: {scenario['name']}")
    console.print(f"  描述: {scenario['description']}")
    console.print(f"  目标类型: {scenario['target_type']}")
    console.print(f"  注入阶段: {scenario['inject_stage']}")
    console.print(f"  执行模式: {scenario['executor_mode']}")
    status_style = "green" if scenario["enabled"] else "red"
    status_text = "启用" if scenario["enabled"] else "禁用"
    console.print(f"  状态: [{status_style}]{status_text}[/{status_style}]")

    # 显示关联配置
    console.print(f"\n[bold]关联配置[/bold]")
    console.print(f"  故障配置ID: {scenario['fault_profile_id']}")
    console.print(f"  验证配置ID: {scenario['validation_profile_id']}")
    console.print(f"  恢复配置ID: {scenario['recovery_profile_id']}")

    # 显示执行统计
    console.print(f"\n[bold]执行统计[/bold]")
    console.print(f"  总执行次数: {scenario['run_count']}")
    console.print(f"  成功次数: {scenario['success_count']}")
    console.print(f"  失败次数: {scenario['failed_count']}")


@scenario_app.command("enable")
def enable_scenario(
    scenario_id: int = typer.Argument(..., help="场景ID"),
) -> None:
    """
    启用场景模板。

    启用后的场景可以被调度执行。
    """
    # TODO: 实际更新数据库
    success = _toggle_scenario_status(scenario_id, enabled=True)

    if success:
        console.print(f"[bold green]✓ 场景 {scenario_id} 已启用[/bold green]")
    else:
        console.print(f"[red]错误: 启用场景 {scenario_id} 失败[/red]")
        raise typer.Exit(code=1)


@scenario_app.command("disable")
def disable_scenario(
    scenario_id: int = typer.Argument(..., help="场景ID"),
) -> None:
    """
    禁用场景模板。

    禁用后的场景不会被调度执行，但保留配置。
    """
    # TODO: 实际更新数据库
    success = _toggle_scenario_status(scenario_id, enabled=False)

    if success:
        console.print(f"[bold green]✓ 场景 {scenario_id} 已禁用[/bold green]")
    else:
        console.print(f"[red]错误: 禁用场景 {scenario_id} 失败[/red]")
        raise typer.Exit(code=1)


@scenario_app.command("clone")
def clone_scenario(
    scenario_id: int = typer.Argument(..., help="要克隆的场景ID"),
    name: Optional[str] = typer.Option(
        None, "--name", "-n", help="新场景名称"
    ),
) -> None:
    """
    克隆场景模板。

    创建现有场景的副本，默认禁用状态。
    """
    # TODO: 从数据库查询原场景
    original = _get_scenario_by_id(scenario_id)

    if not original:
        console.print(f"[red]错误: 未找到ID为 {scenario_id} 的场景模板[/red]")
        raise typer.Exit(code=1)

    # 确定新名称
    new_name = name or f"{original['name']}-clone"

    console.print(Panel(f"[bold cyan]克隆场景模板[/bold cyan]", expand=False))
    console.print(f"[green]原场景:[/green] {original['name']} (ID: {scenario_id})")
    console.print(f"[green]新名称:[/green] {new_name}")

    # TODO: 实际克隆逻辑
    # 1. 复制 ScenarioTemplate 所有字段
    # 2. 生成新名称
    # 3. 关联的 Profile 共享引用
    # 4. 设置 enabled=False

    new_id = _clone_scenario_in_db(scenario_id, new_name)

    console.print(f"\n[bold green]✓ 场景克隆成功！[/bold green]")
    console.print(f"[dim]新场景ID: {new_id}[/dim]")
    console.print(f"[yellow]注意: 克隆的场景默认为禁用状态，请手动启用[/yellow]")


@scenario_app.command("delete")
def delete_scenario(
    scenario_id: int = typer.Argument(..., help="场景ID"),
    force: bool = typer.Option(
        False, "--force", "-f", help="强制删除，不询问确认"
    ),
) -> None:
    """
    删除场景模板。

    注意：删除场景模板不会删除关联的执行记录。
    """
    # TODO: 从数据库查询场景
    scenario = _get_scenario_by_id(scenario_id)

    if not scenario:
        console.print(f"[red]错误: 未找到ID为 {scenario_id} 的场景模板[/red]")
        raise typer.Exit(code=1)

    if not force:
        confirm = typer.confirm(
            f"确定要删除场景 '{scenario['name']}' 吗？",
            default=False,
        )
        if not confirm:
            console.print("[yellow]操作已取消[/yellow]")
            return

    # TODO: 实际删除逻辑
    success = _delete_scenario_from_db(scenario_id)

    if success:
        console.print(f"[bold green]✓ 场景 {scenario_id} 已删除[/bold green]")
    else:
        console.print(f"[red]错误: 删除场景 {scenario_id} 失败[/red]")
        raise typer.Exit(code=1)


# ==================== 模拟数据函数 ====================
# 这些函数将在实际实现时替换为数据库操作

def _get_mock_scenarios(
    enabled_only: bool,
    fault_type: Optional[FaultType],
) -> list[dict]:
    """获取模拟场景列表。"""
    mock_data = [
        {
            "id": 1,
            "name": "存储压力测试",
            "description": "模拟存储空间不足的场景",
            "fault_type": "storage_pressure",
            "target_type": "upgrade",
            "inject_stage": "upgrading",
            "enabled": True,
        },
        {
            "id": 2,
            "name": "低电量阻断测试",
            "description": "模拟低电量条件下的升级阻断",
            "fault_type": "low_battery",
            "target_type": "upgrade",
            "inject_stage": "precheck",
            "enabled": True,
        },
        {
            "id": 3,
            "name": "网络波动测试",
            "description": "测试网络中断和恢复",
            "fault_type": "network_jitter",
            "target_type": "upgrade",
            "inject_stage": "upgrading",
            "enabled": False,
        },
        {
            "id": 4,
            "name": "Monkey稳定性测试",
            "description": "使用Monkey进行稳定性压测",
            "fault_type": "monkey_stability",
            "target_type": "stability",
            "inject_stage": "post_boot",
            "enabled": True,
        },
    ]

    # 应用筛选
    result = mock_data
    if enabled_only:
        result = [s for s in result if s["enabled"]]
    if fault_type:
        result = [s for s in result if s["fault_type"] == fault_type.value]

    return result


def _get_scenario_by_id(scenario_id: int) -> Optional[dict]:
    """根据ID获取场景详情。"""
    mock_data = {
        "id": scenario_id,
        "name": "存储压力测试",
        "description": "模拟存储空间不足的场景，验证系统在低存储条件下的行为",
        "fault_type": "storage_pressure",
        "target_type": "upgrade",
        "inject_stage": "upgrading",
        "executor_mode": "mock",
        "enabled": True,
        "fault_profile_id": 1,
        "validation_profile_id": 1,
        "recovery_profile_id": 1,
        "run_count": 15,
        "success_count": 12,
        "failed_count": 3,
    }
    # 模拟不存在的场景
    if scenario_id > 100:
        return None
    return mock_data


def _create_scenario_in_db(
    name: str,
    fault_type: str,
    description: str,
    target_type: str,
    inject_stage: str,
    executor_mode: str,
) -> int:
    """在数据库中创建场景。"""
    # TODO: 实际数据库操作
    console.print("[dim]正在创建场景模板...[/dim]")
    return 5  # 返回新创建的场景ID


def _toggle_scenario_status(scenario_id: int, enabled: bool) -> bool:
    """切换场景启用状态。"""
    # TODO: 实际数据库操作
    console.print(f"[dim]正在{'启用' if enabled else '禁用'}场景...[/dim]")
    return True


def _clone_scenario_in_db(scenario_id: int, new_name: str) -> int:
    """克隆场景到数据库。"""
    # TODO: 实际数据库操作
    console.print("[dim]正在克隆场景模板...[/dim]")
    return 6  # 返回新场景ID


def _delete_scenario_from_db(scenario_id: int) -> bool:
    """从数据库删除场景。"""
    # TODO: 实际数据库操作
    console.print("[dim]正在删除场景模板...[/dim]")
    return True