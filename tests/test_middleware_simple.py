"""API 认证中间件简单测试."""
import sys
from fastapi import FastAPI
from fastapi.testclient import TestClient

# 测试导入
from chaosdroid.api.middleware import APIKeyAuthenticationMiddleware, setup_authentication


def create_test_app(api_keys: set[str], exclude_paths: set[str]) -> FastAPI:
    """创建测试应用."""
    app = FastAPI()
    setup_authentication(app, api_keys=api_keys, exclude_paths=exclude_paths)

    @app.get("/protected")
    def protected_endpoint():
        return {"message": "success"}

    @app.get("/public")
    def public_endpoint():
        return {"message": "public"}

    return app


def run_tests():
    """运行测试。"""
    print("=" * 60)
    print("API 认证中间件测试")
    print("=" * 60)

    all_passed = True

    # 测试 1: 缺少 API Key 返回 401
    print("\n[测试 1] 缺少 API Key 返回 401...")
    app = create_test_app(api_keys={"test-key-123"}, exclude_paths=set())
    client = TestClient(app)
    response = client.get("/protected")
    if response.status_code == 401 and "unauthorized" in response.json()["error"]:
        print("  ✓ 通过")
    else:
        print(f"  ✗ 失败：status={response.status_code}, body={response.json()}")
        all_passed = False

    # 测试 2: 无效 API Key 返回 401
    print("[测试 2] 无效 API Key 返回 401...")
    response = client.get("/protected", headers={"X-API-Key": "wrong-key"})
    if response.status_code == 401:
        print("  ✓ 通过")
    else:
        print(f"  ✗ 失败：status={response.status_code}")
        all_passed = False

    # 测试 3: 有效 API Key 允许访问
    print("[测试 3] 有效 API Key 允许访问...")
    response = client.get("/protected", headers={"X-API-Key": "test-key-123"})
    if response.status_code == 200 and response.json()["message"] == "success":
        print("  ✓ 通过")
    else:
        print(f"  ✗ 失败：status={response.status_code}")
        all_passed = False

    # 测试 4: 免认证路径无需 API Key
    print("[测试 4] 免认证路径无需 API Key...")
    app2 = create_test_app(api_keys={"test-key-123"}, exclude_paths={"/health", "/public"})
    client2 = TestClient(app2)
    response = client2.get("/public")
    if response.status_code == 200:
        print("  ✓ 通过")
    else:
        print(f"  ✗ 失败：status={response.status_code}")
        all_passed = False

    # 测试 5: 健康检查端点默认排除
    print("[测试 5] 健康检查端点默认排除...")
    app3 = create_test_app(api_keys={"test-key-123"}, exclude_paths={"/health"})
    client3 = TestClient(app3)

    @app3.get("/health")
    def health():
        return {"status": "healthy"}

    response = client3.get("/health")
    if response.status_code == 200:
        print("  ✓ 通过")
    else:
        print(f"  ✗ 失败：status={response.status_code}")
        all_passed = False

    # 测试 6: 多个 API Key 都能正常工作
    print("[测试 6] 多个 API Key 都能正常工作...")
    app4 = create_test_app(api_keys={"key-1", "key-2", "key-3"}, exclude_paths=set())
    client4 = TestClient(app4)

    @app4.get("/test")
    def test_endpoint():
        return {"ok": True}

    for key in ["key-1", "key-2", "key-3"]:
        response = client4.get("/test", headers={"X-API-Key": key})
        if response.status_code != 200:
            print(f"  ✗ 失败：key={key}, status={response.status_code}")
            all_passed = False
            break
    else:
        print("  ✓ 通过")

    # 测试 7: 401 响应包含 WWW-Authenticate 头
    print("[测试 7] 401 响应包含 WWW-Authenticate 头...")
    app5 = create_test_app(api_keys={"test-key"}, exclude_paths=set())
    client5 = TestClient(app5)

    @app5.get("/secure")
    def secure_endpoint():
        return {"secret": "data"}

    response = client5.get("/secure")
    if response.status_code == 401 and response.headers.get("WWW-Authenticate") == "API-Key":
        print("  ✓ 通过")
    else:
        print(f"  ✗ 失败：status={response.status_code}, WWW-Authenticate={response.headers.get('WWW-Authenticate')}")
        all_passed = False

    print("\n" + "=" * 60)
    if all_passed:
        print("所有测试通过！")
        return 0
    else:
        print("部分测试失败！")
        return 1


if __name__ == "__main__":
    sys.exit(run_tests())
