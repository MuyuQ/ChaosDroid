"""API 认证中间件测试.

测试 API Key 认证中间件的功能。
"""
import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

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


class TestAPIKeyAuthentication:
    """API Key 认证测试类."""

    def test_missing_api_key_returns_401(self):
        """测试缺少 API Key 时返回 401."""
        app = create_test_app(
            api_keys={"test-key-123"},
            exclude_paths=set()
        )
        client = TestClient(app)

        response = client.get("/protected")

        assert response.status_code == 401
        assert "unauthorized" in response.json()["error"]

    def test_invalid_api_key_returns_401(self):
        """测试无效 API Key 返回 401."""
        app = create_test_app(
            api_keys={"test-key-123"},
            exclude_paths=set()
        )
        client = TestClient(app)

        response = client.get(
            "/protected",
            headers={"X-API-Key": "wrong-key"}
        )

        assert response.status_code == 401
        assert "unauthorized" in response.json()["error"]

    def test_valid_api_key_allows_access(self):
        """测试有效 API Key 允许访问."""
        app = create_test_app(
            api_keys={"test-key-123", "another-key-456"},
            exclude_paths=set()
        )
        client = TestClient(app)

        response = client.get(
            "/protected",
            headers={"X-API-Key": "test-key-123"}
        )

        assert response.status_code == 200
        assert response.json()["message"] == "success"

    def test_excluded_path_allows_access_without_key(self):
        """测试免认证路径无需 API Key."""
        app = create_test_app(
            api_keys={"test-key-123"},
            exclude_paths={"/health", "/public"}
        )
        client = TestClient(app)

        # 访问排除路径
        response = client.get("/public")
        assert response.status_code == 200

        # 访问受保护路径
        response = client.get("/protected")
        assert response.status_code == 401

    def test_health_endpoint_excluded_by_default(self):
        """测试健康检查端点默认排除."""
        app = create_test_app(
            api_keys={"test-key-123"},
            exclude_paths={"/health"}
        )
        client = TestClient(app)

        response = client.get("/health")
        assert response.status_code == 200

    def test_multiple_api_keys_work(self):
        """测试多个 API Key 都能正常工作."""
        app = create_test_app(
            api_keys={"key-1", "key-2", "key-3"},
            exclude_paths=set()
        )
        client = TestClient(app)

        for key in ["key-1", "key-2", "key-3"]:
            response = client.get(
                "/protected",
                headers={"X-API-Key": key}
            )
            assert response.status_code == 200

    def test_401_response_has_www_authenticate_header(self):
        """测试 401 响应包含 WWW-Authenticate 头."""
        app = create_test_app(
            api_keys={"test-key"},
            exclude_paths=set()
        )
        client = TestClient(app)

        response = client.get("/protected")

        assert response.status_code == 401
        assert response.headers.get("WWW-Authenticate") == "API-Key"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
