#!/usr/bin/env python
"""ChaosDroid 部署验证脚本。

检查所有必要的组件是否已正确部署。
"""
import sys
import os
from pathlib import Path

def check_mark(passed):
    return "✅" if passed else "❌"

def main():
    print("=" * 60)
    print("ChaosDroid 部署验证")
    print("=" * 60)

    checks = []

    # 1. 检查 Python 版本
    print(f"\n[1] Python 版本：{sys.version.split()[0]}")
    checks.append(("Python 3.10+", sys.version_info >= (3, 10)))

    # 2. 检查必要文件
    print("\n[2] 检查项目文件...")
    required_files = [
        "pyproject.toml",
        "start_server.py",
        "app/api/main.py",
        ".env.example",
        ".env.production",
        "Dockerfile",
        "docker-compose.yml",
        "deploy.sh",
        "deploy.bat",
    ]
    for f in required_files:
        exists = Path(f).exists()
        print(f"  {check_mark(exists)} {f}")
        checks.append((f, exists))

    # 3. 检查依赖
    print("\n[3] 检查依赖包...")
    deps = [
        ("fastapi", "fastapi"),
        ("uvicorn", "uvicorn"),
        ("sqlalchemy", "sqlalchemy"),
        ("aiosqlite", "aiosqlite"),
        ("pydantic", "pydantic"),
        ("jinja2", "jinja2"),
        ("pyyaml", "yaml"),  # pyyaml 安装后导入名为 yaml
    ]
    for pkg_name, import_name in deps:
        try:
            __import__(import_name)
            print(f"  ✅ {pkg_name}")
            checks.append((pkg_name, True))
        except ImportError:
            print(f"  ❌ {pkg_name}")
            checks.append((pkg_name, False))

    # 4. 检查应用模块
    print("\n[4] 检查应用模块...")
    modules = [
        "app.api.main",
        "app.models.event_queue",
        "app.services.event_dispatcher",
        "app.services.log_export_service",
        "app.diagnosis.services.trigger",
        "app.workers.diagnosis_worker",
    ]
    for mod in modules:
        try:
            __import__(mod)
            print(f"  ✅ {mod}")
            checks.append((mod, True))
        except ImportError as e:
            print(f"  ❌ {mod}: {e}")
            checks.append((mod, False))

    # 5. 检查目录
    print("\n[5] 检查目录结构...")
    dirs = ["logs", "data", "artifacts", "reports", "migrations"]
    for d in dirs:
        exists = Path(d).exists()
        print(f"  {check_mark(exists)} {d}")
        checks.append((d, exists))

    # 6. 检查数据库
    print("\n[6] 检查数据库...")
    db_exists = Path("chaosdroid.db").exists()
    print(f"  {check_mark(db_exists)} chaosdroid.db")
    checks.append(("chaosdroid.db", db_exists))

    # 7. 总结
    print("\n" + "=" * 60)
    passed = sum(1 for _, p in checks if p)
    total = len(checks)
    print(f"验证结果：{passed}/{total} 通过")

    if passed == total:
        print("✅ 部署验证通过！")
        print("\n启动命令:")
        print("  python start_server.py")
        print("\n访问地址:")
        print("  http://localhost:8000")
    else:
        print("❌ 部分检查未通过，请检查上述输出")
        return 1

    print("=" * 60)
    return 0

if __name__ == "__main__":
    sys.exit(main())
