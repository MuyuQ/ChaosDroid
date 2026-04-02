"""
设备管理 CLI 命令模块。

提供设备列表、状态检查等功能。
"""
from typing import Optional
from datetime import datetime

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import print as rprint

# 创建 Typer 应用
device_app = typer.Typer(
    name="device",
    help="设备管理命令",
    add_completion=False,
)

console = Console()


@device_app.command("list")
def list_devices(
    online_only: bool = typer.Option(
        False, "--online-only", "-o", help="仅显示在线设备"
    ),
) -> None:
    """
    列出所有设备。

    显示设备序列号、状态、型号等信息。
    """
    # TODO: 实际获取设备列表
    # 可以通过 adb devices 或其他方式获取
    devices = _get_mock_devices(online_only)

    if not devices:
        console.print("[yellow]未找到任何设备[/yellow]")
        return

    # 创建表格
    table = Table(title="设备列表", show_header=True, header_style="bold cyan")
    table.add_column("序列号", style="green")
    table.add_column("状态", style="bold")
    table.add_column("型号", style="blue")
    table.add_column("Android版本", style="magenta")
    table.add_column("电量", style="yellow")
    table.add_column("存储可用", style="cyan")

    for device in devices:
        status_style = "green" if device["online"] else "red"
        status_text = "在线" if device["online"] else "离线"
        battery_style = _get_battery_style(device["battery_level"])

        table.add_row(
            device["serial"],
            f"[{status_style}]{status_text}[/{status_style}]",
            device["model"],
            device["android_version"],
            f"[{battery_style}]{device['battery_level']}%[/{battery_style}]",
            device["storage_available"],
        )

    console.print(table)
    console.print(f"\n[dim]共 {len(devices)} 台设备[/dim]")


@device_app.command("check")
def check_device(
    serial: str = typer.Argument(..., help="设备序列号"),
) -> None:
    """
    检查设备状态。

    显示设备详细信息，包括电量、存储、系统属性等。
    """
    # TODO: 实际设备检查逻辑
    device = _check_device_status(serial)

    if not device:
        console.print(f"[red]错误: 未找到设备 {serial}[/red]")
        raise typer.Exit(code=1)

    if not device["online"]:
        console.print(f"[red]错误: 设备 {serial} 当前离线[/red]")
        raise typer.Exit(code=1)

    # 显示设备详情
    console.print(Panel(f"[bold cyan]设备状态检查[/bold cyan]", expand=False))
    console.print(f"\n[bold]基本信息[/bold]")
    console.print(f"  序列号: {device['serial']}")
    console.print(f"  状态: [green]在线[/green]")
    console.print(f"  型号: {device['model']}")
    console.print(f"  制造商: {device['manufacturer']}")
    console.print(f"  Android版本: {device['android_version']}")
    console.print(f"  SDK版本: {device['sdk_version']}")
    console.print(f"  CPU架构: {device['cpu_abi']}")

    # 显示电量信息
    console.print(f"\n[bold]电量信息[/bold]")
    battery_style = _get_battery_style(device["battery_level"])
    console.print(f"  电量: [{battery_style}]{device['battery_level']}%[/{battery_style}]")
    console.print(f"  充电状态: {'是' if device['charging'] else '否'}")
    console.print(f"  电池温度: {device['battery_temperature']}°C")

    # 显示存储信息
    console.print(f"\n[bold]存储信息[/bold]")
    console.print(f"  总存储: {device['storage_total']}")
    console.print(f"  已使用: {device['storage_used']}")
    console.print(f"  可用: {device['storage_available']}")
    console.print(f"  使用率: {device['storage_percent']}%")

    # 显示系统状态
    console.print(f"\n[bold]系统状态[/bold]")
    boot_completed = device.get("boot_completed", True)
    boot_style = "green" if boot_completed else "red"
    console.print(f"  Boot完成: [{boot_style}]{'是' if boot_completed else '否'}[/{boot_style}]")
    console.print(f"  运行时间: {device['uptime']}")
    console.print(f"  网络连接: {'是' if device['network_connected'] else '否'}")

    # 显示检查建议
    console.print(f"\n[bold]检查建议[/bold]")
    _display_recommendations(device)


def _get_battery_style(level: int) -> str:
    """获取电量对应的样式。"""
    if level >= 50:
        return "green"
    elif level >= 20:
        return "yellow"
    else:
        return "red"


def _display_recommendations(device: dict) -> None:
    """显示设备检查建议。"""
    recommendations = []

    # 电量检查
    if device["battery_level"] < 20:
        recommendations.append(
            ("warning", "电量低于20%，建议充电后再执行测试")
        )
    elif device["battery_level"] < 50:
        recommendations.append(
            ("info", "电量在20-50%之间，适合执行低电量相关测试")
        )

    # 存储检查
    storage_percent = device.get("storage_percent", 0)
    if storage_percent > 90:
        recommendations.append(
            ("error", "存储空间严重不足，建议清理后再执行测试")
        )
    elif storage_percent > 80:
        recommendations.append(
            ("warning", "存储空间紧张，可能影响某些测试")
        )

    # 网络检查
    if not device.get("network_connected"):
        recommendations.append(
            ("warning", "设备未连接网络，网络相关测试将无法执行")
        )

    # Boot状态检查
    if not device.get("boot_completed"):
        recommendations.append(
            ("error", "设备尚未完成启动，请等待后再执行测试")
        )

    if recommendations:
        for level, msg in recommendations:
            if level == "error":
                console.print(f"  [red]✗ {msg}[/red]")
            elif level == "warning":
                console.print(f"  [yellow]! {msg}[/yellow]")
            else:
                console.print(f"  [blue]ℹ {msg}[/blue]")
    else:
        console.print(f"  [green]✓ 设备状态良好，可以执行测试[/green]")


# ==================== 模拟数据函数 ====================

def _get_mock_devices(online_only: bool) -> list[dict]:
    """获取模拟设备列表。"""
    mock_data = [
        {
            "serial": "emulator-5554",
            "online": True,
            "model": "sdk_gphone64_x86_64",
            "android_version": "14",
            "battery_level": 85,
            "storage_available": "1.2 GB",
        },
        {
            "serial": "emulator-5556",
            "online": True,
            "model": "sdk_gphone64_x86_64",
            "android_version": "13",
            "battery_level": 45,
            "storage_available": "512 MB",
        },
        {
            "serial": "real-device-001",
            "online": False,
            "model": "Pixel 7",
            "android_version": "14",
            "battery_level": 0,
            "storage_available": "N/A",
        },
    ]

    if online_only:
        return [d for d in mock_data if d["online"]]
    return mock_data


def _check_device_status(serial: str) -> Optional[dict]:
    """检查设备状态。"""
    # 模拟不存在的设备
    if serial == "not-exist":
        return None

    # 模拟离线设备
    if serial == "offline-device":
        return {
            "serial": serial,
            "online": False,
        }

    # 返回在线设备的详细信息
    return {
        "serial": serial,
        "online": True,
        "model": "sdk_gphone64_x86_64",
        "manufacturer": "Google",
        "android_version": "14",
        "sdk_version": "34",
        "cpu_abi": "x86_64",
        "battery_level": 85,
        "charging": True,
        "battery_temperature": 28.5,
        "storage_total": "16 GB",
        "storage_used": "12 GB",
        "storage_available": "4 GB",
        "storage_percent": 75,
        "boot_completed": True,
        "uptime": "2天 5小时 30分钟",
        "network_connected": True,
    }