"""Tests for CORS configuration (SEC-014).

Verifies that CORS middleware uses explicit method and header lists
instead of wildcards, preventing overly permissive cross-origin access.
"""

import pytest
from unittest.mock import patch, MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.cors_config import configure_cors, ALLOWED_METHODS, ALLOWED_HEADERS


@pytest.fixture
def app():
    """Create a test FastAPI app with CORS configured."""
    test_app = FastAPI()

    @test_app.get("/test")
    def test_endpoint():
        return {"status": "ok"}

    @test_app.post("/test")
    def test_post():
        return {"status": "created"}

    @test_app.put("/test")
    def test_put():
        return {"status": "updated"}

    @test_app.patch("/test")
    def test_patch():
        return {"status": "patched"}

    @test_app.delete("/test")
    def test_delete():
        return {"status": "deleted"}

    with patch("src.api.cors_config.settings") as mock_settings:
        mock_settings.CORS_ORIGINS = "http://localhost:3000,http://localhost:5173"
        configure_cors(test_app)

    return test_app


@pytest.fixture
def client(app):
    return TestClient(app)


# --- Module-level constant tests ---

class TestAllowedMethods:
    """Verify the explicit allowed methods list."""

    def test_includes_get(self):
        assert "GET" in ALLOWED_METHODS

    def test_includes_post(self):
        assert "POST" in ALLOWED_METHODS

    def test_includes_put(self):
        assert "PUT" in ALLOWED_METHODS

    def test_includes_patch(self):
        assert "PATCH" in ALLOWED_METHODS

    def test_includes_delete(self):
        assert "DELETE" in ALLOWED_METHODS

    def test_includes_options(self):
        assert "OPTIONS" in ALLOWED_METHODS

    def test_no_wildcard(self):
        assert "*" not in ALLOWED_METHODS

    def test_no_head(self):
        """HEAD is not needed by the frontend and should not be allowed."""
        assert "HEAD" not in ALLOWED_METHODS

    def test_no_trace(self):
        """TRACE should never be allowed — used for XST attacks."""
        assert "TRACE" not in ALLOWED_METHODS

    def test_no_connect(self):
        """CONNECT should never be allowed via CORS."""
        assert "CONNECT" not in ALLOWED_METHODS


class TestAllowedHeaders:
    """Verify the explicit allowed headers list."""

    def test_includes_authorization(self):
        assert "Authorization" in ALLOWED_HEADERS

    def test_includes_content_type(self):
        assert "Content-Type" in ALLOWED_HEADERS

    def test_includes_accept(self):
        assert "Accept" in ALLOWED_HEADERS

    def test_includes_x_api_key(self):
        assert "X-API-Key" in ALLOWED_HEADERS

    def test_includes_x_webhook_signature(self):
        assert "X-Webhook-Signature" in ALLOWED_HEADERS

    def test_includes_x_webhook_source(self):
        assert "X-Webhook-Source" in ALLOWED_HEADERS

    def test_includes_x_idempotency_key(self):
        assert "X-Idempotency-Key" in ALLOWED_HEADERS

    def test_includes_x_request_id(self):
        assert "X-Request-ID" in ALLOWED_HEADERS

    def test_no_wildcard(self):
        assert "*" not in ALLOWED_HEADERS


class TestCorsMiddlewareIntegration:
    """Test CORS middleware behavior with explicit configurations."""

    def test_preflight_allowed_origin(self, client):
        """Preflight from allowed origin should succeed."""
        response = client.options(
            "/test",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Authorization,Content-Type",
            },
        )
        assert response.status_code == 200
        assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"

    def test_preflight_disallowed_origin(self, client):
        """Preflight from unknown origin should be rejected."""
        response = client.options(
            "/test",
            headers={
                "Origin": "http://evil.com",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Authorization",
            },
        )
        # CORSMiddleware returns 400 for disallowed origins
        assert response.headers.get("access-control-allow-origin") is None

    def test_preflight_returns_allowed_methods(self, client):
        """Preflight response should list allowed methods."""
        response = client.options(
            "/test",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
            },
        )
        allow_methods = response.headers.get("access-control-allow-methods", "")
        for method in ALLOWED_METHODS:
            assert method in allow_methods

    def test_preflight_allowed_header(self, client):
        """Preflight requesting an allowed header should succeed."""
        response = client.options(
            "/test",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "Authorization",
            },
        )
        assert response.status_code == 200
        allow_headers = response.headers.get("access-control-allow-headers", "")
        assert "Authorization" in allow_headers

    def test_preflight_disallowed_header(self, client):
        """Preflight requesting a non-allowed header should be rejected."""
        response = client.options(
            "/test",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "X-Evil-Header",
            },
        )
        # CORSMiddleware returns 400 for disallowed headers
        allow_headers = response.headers.get("access-control-allow-headers", "")
        assert "X-Evil-Header" not in allow_headers

    def test_simple_get_with_allowed_origin(self, client):
        """Simple GET from allowed origin should include CORS headers."""
        response = client.get(
            "/test",
            headers={"Origin": "http://localhost:3000"},
        )
        assert response.status_code == 200
        assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"
        assert response.headers.get("access-control-allow-credentials") == "true"

    def test_simple_get_with_disallowed_origin(self, client):
        """GET from disallowed origin should not include CORS allow header."""
        response = client.get(
            "/test",
            headers={"Origin": "http://evil.com"},
        )
        assert response.headers.get("access-control-allow-origin") is None

    def test_post_with_allowed_origin(self, client):
        """POST from allowed origin should work."""
        response = client.post(
            "/test",
            headers={"Origin": "http://localhost:3000"},
        )
        assert response.status_code == 200
        assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"

    def test_credentials_allowed(self, client):
        """CORS should allow credentials (cookies/auth headers)."""
        response = client.get(
            "/test",
            headers={"Origin": "http://localhost:3000"},
        )
        assert response.headers.get("access-control-allow-credentials") == "true"

    def test_second_allowed_origin(self, client):
        """Second configured origin should also be allowed."""
        response = client.get(
            "/test",
            headers={"Origin": "http://localhost:5173"},
        )
        assert response.status_code == 200
        assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"


class TestSourceCodeVerification:
    """Verify the source code doesn't contain wildcards."""

    def test_no_wildcard_methods_in_source(self):
        """cors_config.py should not use allow_methods=['*']."""
        import inspect
        source = inspect.getsource(configure_cors)
        # The function should reference ALLOWED_METHODS, not "*"
        assert "ALLOWED_METHODS" in source
        assert 'allow_methods=["*"]' not in source
        assert "allow_methods=['*']" not in source

    def test_no_wildcard_headers_in_source(self):
        """cors_config.py should not use allow_headers=['*']."""
        import inspect
        source = inspect.getsource(configure_cors)
        assert "ALLOWED_HEADERS" in source
        assert 'allow_headers=["*"]' not in source
        assert "allow_headers=['*']" not in source

    def test_credentials_enabled(self):
        """cors_config.py should enable allow_credentials."""
        import inspect
        source = inspect.getsource(configure_cors)
        assert "allow_credentials=True" in source
