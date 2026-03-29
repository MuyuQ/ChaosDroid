"""
Web 服务 CLI 命令模块。

提供启动 Web 服务器的功能。
"""
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel

console = Console()


def serve_cmd(
    port: int = typer.Option(
        8000, "--port", "-p", help="服务监听端口"
    ),
    host: str = typer.Option(
        "127.0.0.1", "--host", "-h", help="服务监听地址"
    ),
    reload: bool = typer.Option(
        False, "--reload", "-r", help="开发模式（自动重载）"
    ),
    workers: int = typer.Option(
        1, "--workers", "-w", help="工作进程数量"
    ),
) -> None:
    """
    启动 ChaosDroid Web 服务。

    提供 Web UI 和 REST API 接口。
    """
    console.print(Panel(f"[bold cyan]ChaosDroid Web 服务[/bold cyan]", expand=False))
    console.print(f"\n[green]启动配置[/green]")
    console.print(f"  监听地址: {host}")
    console.print(f"  监听端口: {port}")
    console.print(f"  工作进程: {workers}")
    console.print(f"  开发模式: {'是' if reload else '否'}")

    # 检查端口是否可用
    if not _check_port_available(host, port):
        console.print(f"\n[red]错误: 端口 {port} 已被占用[/red]")
        console.print(f"[dim]请使用 --port 指定其他端口[/dim]")
        raise typer.Exit(code=1)

    # 初始化检查
    console.print(f"\n[dim]正在初始化服务...[/dim]")

    if not _check_database_ready():
        console.print(f"[yellow]警告: 数据库未初始化，请先运行 'chaosdroid init'[/yellow]")

    if not _check_directories_ready():
        console.print(f"[yellow]警告: 必要目录不存在，正在创建...[/yellow]")
        _create_directories()

    # 显示访问地址
    console.print(f"\n[bold green]✓ 服务启动成功！[/bold green]")
    console.print(f"  Web UI: [blue]http://{host}:{port}/[/blue]")
    console.print(f"  API 文档: [blue]http://{host}:{port}/docs[/blue]")
    console.print(f"\n[dim]按 Ctrl+C 停止服务[/dim]")

    # 启动服务
    try:
        _start_server(host, port, reload, workers)
    except KeyboardInterrupt:
        console.print(f"\n[yellow]服务已停止[/yellow]")


# ==================== 辅助函数 ====================

def _check_port_available(host: str, port: int) -> bool:
    """检查端口是否可用。"""
    import socket

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind((host, port))
            return True
    except OSError:
        return False


def _check_database_ready() -> bool:
    """检查数据库是否已初始化。"""
    # TODO: 实际检查数据库是否存在
    from pathlib import Path
    db_path = Path("chaosdroid.db")
    return db_path.exists()


def _check_directories_ready() -> bool:
    """检查必要目录是否存在。"""
    from pathlib import Path
    required_dirs = ["artifacts", "reports", "logs"]
    return all(Path(d).exists() for d in required_dirs)


def _create_directories() -> None:
    """创建必要目录。"""
    from pathlib import Path
    required_dirs = ["artifacts", "reports", "logs"]
    for d in required_dirs:
        Path(d).mkdir(parents=True, exist_ok=True)
    console.print(f"[dim]已创建目录: {', '.join(required_dirs)}[/dim]")


def _start_server(host: str, port: int, reload: bool, workers: int) -> None:
    """启动 Web 服务器。"""
    try:
        import uvicorn

        # 使用 uvicorn 启动 FastAPI 应用
        uvicorn.run(
            "chaosdroid.api.main:app",
            host=host,
            port=port,
            reload=reload,
            workers=workers if not reload else 1,  # reload 模式不支持多进程
            log_level="info",
        )
    except ImportError:
        console.print("[red]错误: uvicorn 未安装[/red]")
        console.print("[dim]请运行: pip install uvicorn[/dim]")
        raise typer.Exit(code=1)
    except Exception as e:
        console.print(f"[red]启动服务失败: {e}[/red]")
        raise typer.Exit(code=1)