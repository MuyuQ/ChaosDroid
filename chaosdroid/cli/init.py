"""
初始化 CLI 命令模块。

提供数据库初始化和目录结构创建功能。
"""
import asyncio
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()


def init_cmd(
    force: bool = typer.Option(
        False, "--force", "-f", help="强制重新初始化（会覆盖现有数据）"
    ),
    db_path: str = typer.Option(
        "chaosdroid.db", "--db-path", help="数据库文件路径"
    ),
    artifacts_dir: str = typer.Option(
        "artifacts", "--artifacts-dir", help="执行产物存储目录"
    ),
    reports_dir: str = typer.Option(
        "reports", "--reports-dir", help="报告存储目录"
    ),
) -> None:
    """
    初始化 ChaosDroid。

    创建数据库表结构和必要的目录结构。
    """
    console.print(Panel(f"[bold cyan]ChaosDroid 初始化[/bold cyan]", expand=False))
    console.print(f"\n[green]初始化配置[/green]")
    console.print(f"  数据库路径: {db_path}")
    console.print(f"  产物目录: {artifacts_dir}")
    console.print(f"  报告目录: {reports_dir}")
    console.print(f"  强制模式: {'是' if force else '否'}")

    # 检查是否已初始化
    if _is_already_initialized(db_path) and not force:
        console.print(f"\n[yellow]警告: 数据库已存在[/yellow]")
        console.print(f"[dim]使用 --force 参数强制重新初始化[/dim]")

        if not typer.confirm("是否继续初始化？这不会影响现有数据", default=False):
            console.print("[yellow]操作已取消[/yellow]")
            return

    # 创建目录结构
    console.print(f"\n[bold]创建目录结构[/bold]")
    _create_directory_structure(artifacts_dir, reports_dir)

    # 初始化数据库
    console.print(f"\n[bold]初始化数据库[/bold]")
    _initialize_database(db_path, force)

    # 创建默认配置
    console.print(f"\n[bold]创建默认配置[/bold]")
    _create_default_profiles()

    # 显示初始化结果
    console.print(f"\n[bold green]✓ 初始化完成！[/bold green]")

    # 显示后续步骤
    _show_next_steps()


def _is_already_initialized(db_path: str) -> bool:
    """检查是否已初始化。"""
    return Path(db_path).exists()


def _create_directory_structure(artifacts_dir: str, reports_dir: str) -> None:
    """创建目录结构。"""
    directories = [
        artifacts_dir,
        reports_dir,
        "logs",
        "templates",
    ]

    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("目录", style="green")
    table.add_column("状态", style="bold")

    for dir_name in directories:
        dir_path = Path(dir_name)
        try:
            dir_path.mkdir(parents=True, exist_ok=True)
            table.add_row(dir_name, "[green]✓ 已创建[/green]")
        except Exception as e:
            table.add_row(dir_name, f"[red]✗ 失败: {e}[/red]")

    console.print(table)


def _initialize_database(db_path: str, force: bool) -> None:
    """初始化数据库。"""
    db_file = Path(db_path)

    # 如果强制模式且数据库存在，先删除
    if force and db_file.exists():
        db_file.unlink()
        console.print(f"[dim]已删除旧数据库文件[/dim]")

    try:
        # 使用异步数据库模块初始化
        from chaosdroid.models import init_engine, create_tables, close_engine

        # 初始化引擎
        init_engine(db_path)
        console.print(f"[dim]数据库引擎初始化完成[/dim]")

        # 创建表结构（异步操作）
        asyncio.run(create_tables())
        console.print(f"[green]✓ 数据库表结构创建成功[/green]")

        # 显示创建的表
        tables = [
            "scenario_templates",
            "fault_profiles",
            "validation_profiles",
            "recovery_profiles",
            "scenario_runs",
            "scenario_steps",
            "artifacts",
            "reports",
        ]
        console.print(f"[dim]创建的表: {', '.join(tables)}[/dim]")

        # 关闭引擎
        asyncio.run(close_engine())

    except ImportError:
        console.print(f"[yellow]警告: 数据库模型模块尚未完全实现[/yellow]")
        console.print(f"[dim]使用同步模式创建数据库结构...[/dim]")
        _create_sync_database(db_path)
        console.print(f"[green]✓ 数据库创建成功[/green]")

    except Exception as e:
        console.print(f"[red]✗ 数据库初始化失败: {e}[/red]")
        raise typer.Exit(code=1)


def _create_sync_database(db_path: str) -> None:
    """使用同步 SQLite 创建数据库（备用方案）。"""
    import sqlite3

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 创建基础表结构
    cursor.executescript("""
        CREATE TABLE IF NOT EXISTS scenario_templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            target_type TEXT,
            fault_profile_id INTEGER,
            validation_profile_id INTEGER,
            recovery_profile_id INTEGER,
            inject_stage TEXT,
            executor_mode TEXT DEFAULT 'mock',
            enabled INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS fault_profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            fault_type TEXT NOT NULL,
            parameters JSON,
            safe_cleanup_required INTEGER DEFAULT 0,
            risk_level TEXT DEFAULT 'low',
            is_active INTEGER DEFAULT 1,
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS validation_profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            checks_json TEXT,
            timeout_sec INTEGER DEFAULT 180,
            pass_rules_json TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS recovery_profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            steps_json TEXT,
            manual_intervention_allowed INTEGER DEFAULT 0,
            timeout_sec INTEGER DEFAULT 300,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS scenario_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scenario_template_id INTEGER,
            device_serial TEXT,
            status TEXT DEFAULT 'queued',
            started_at TIMESTAMP,
            finished_at TIMESTAMP,
            inject_stage TEXT,
            result_summary_json TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (scenario_template_id) REFERENCES scenario_templates(id)
        );

        CREATE TABLE IF NOT EXISTS scenario_steps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scenario_run_id INTEGER,
            step_type TEXT,
            step_order INTEGER,
            status TEXT,
            started_at TIMESTAMP,
            finished_at TIMESTAMP,
            summary_json TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (scenario_run_id) REFERENCES scenario_runs(id)
        );

        CREATE TABLE IF NOT EXISTS artifacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scenario_run_id INTEGER,
            step_id INTEGER,
            artifact_type TEXT,
            path TEXT,
            size INTEGER,
            meta_json TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (scenario_run_id) REFERENCES scenario_runs(id),
            FOREIGN KEY (step_id) REFERENCES scenario_steps(id)
        );

        CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scenario_run_id INTEGER,
            markdown_path TEXT,
            html_path TEXT,
            summary_json TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (scenario_run_id) REFERENCES scenario_runs(id)
        );
    """)

    conn.commit()
    conn.close()


def _create_default_profiles() -> None:
    """创建默认配置。"""
    # TODO: 创建默认的 FaultProfile、ValidationProfile、RecoveryProfile
    default_profiles = [
        ("存储压力测试", "storage_pressure", "low"),
        ("低电量测试", "low_battery", "low"),
        ("网络波动测试", "network_jitter", "medium"),
        ("重启超时测试", "reboot_timeout", "high"),
        ("CPU/IO压力测试", "cpu_io_stress", "medium"),
        ("Monkey稳定性测试", "monkey_stability", "medium"),
    ]

    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("配置名称", style="green")
    table.add_column("故障类型", style="blue")
    table.add_column("风险等级", style="yellow")
    table.add_column("状态", style="bold")

    for name, fault_type, risk_level in default_profiles:
        table.add_row(name, fault_type, risk_level, "[dim]待创建[/dim]")

    console.print(table)
    console.print(f"[dim]注: 默认配置将在首次使用时自动创建[/dim]")


def _show_next_steps() -> None:
    """显示后续步骤。"""
    console.print(f"\n[bold]后续步骤[/bold]")
    console.print(f"  1. 创建场景模板:")
    console.print(f"     [blue]chaosdroid scenario create --name \"测试场景\" --fault-type storage_pressure[/blue]")
    console.print(f"  2. 检查设备状态:")
    console.print(f"     [blue]chaosdroid device list[/blue]")
    console.print(f"  3. 执行场景:")
    console.print(f"     [blue]chaosdroid run execute <scenario-id> --device <serial>[/blue]")
    console.print(f"  4. 启动 Web 服务:")
    console.print(f"     [blue]chaosdroid serve --port 8000[/blue]")