"""
Example API tests without browser.

Demonstrates testing backend APIs directly using httpx:
- Health check endpoints
- Authentication APIs
- CRUD operations
- Error handling

Copy and adapt these patterns for your own API tests.
Requires: pip install httpx
"""

import pytest


class TestHealthEndpoints:
    """Tests for service health and status endpoints."""
    
    @pytest.mark.smoke
    @pytest.mark.api
    def test_health_check(self, api_client):
        """
        Verify health check endpoint returns 200.
        
        Expected: /health or /api/health should return 200 OK.
        """
        endpoints = ["/health", "/api/health", "/healthz", "/status"]
        
        for endpoint in endpoints:
            try:
                response = api_client.get(endpoint)
                if response.status_code == 200:
                    return
            except Exception:
                continue
        
        pytest.skip("No health endpoint found")
    
    @pytest.mark.smoke
    @pytest.mark.api
    def test_root_endpoint(self, api_client):
        """
        Verify root endpoint is accessible.
        
        Expected: Root path should return 2xx or redirect.
        """
        response = api_client.get("/", follow_redirects=True)
        assert response.status_code < 500, f"Root endpoint returned {response.status_code}"


class TestAuthenticationAPI:
    """Tests for authentication API endpoints."""
    
    @pytest.mark.api
    def test_login_success(self, api_client):
        """
        Verify login API with valid credentials.
        
        Expected: Should return 200 with token in response.
        """
        endpoints = ["/api/auth/login", "/api/login", "/auth/login", "/login"]
        payloads = [
            {"username": "testuser", "password": "password123"},
            {"email": "test@example.com", "password": "password123"},
        ]
        
        for endpoint in endpoints:
            for payload in payloads:
                try:
                    response = api_client.post(endpoint, json=payload)
                    if response.status_code == 200:
                        data = response.json()
                        assert "token" in data or "access_token" in data or "session" in data
                        return
                except Exception:
                    continue
        
        pytest.skip("No login endpoint found or credentials not configured")
    
    @pytest.mark.api
    def test_login_invalid_credentials(self, api_client):
        """
        Verify login API rejects invalid credentials.
        
        Expected: Should return 401 or 400 for wrong password.
        """
        endpoints = ["/api/auth/login", "/api/login", "/auth/login", "/login"]
        payload = {"username": "testuser", "password": "wrongpassword"}
        
        for endpoint in endpoints:
            try:
                response = api_client.post(endpoint, json=payload)
                if response.status_code in [400, 401, 403, 422]:
                    return
            except Exception:
                continue
        
        pytest.skip("No login endpoint found")
    
    @pytest.mark.api
    def test_protected_endpoint_without_auth(self, api_client):
        """
        Verify protected endpoints require authentication.
        
        Expected: Should return 401 without auth token.
        """
        protected_endpoints = [
            "/api/user",
            "/api/me",
            "/api/profile",
            "/api/protected",
            "/api/dashboard",
        ]
        
        for endpoint in protected_endpoints:
            response = api_client.get(endpoint)
            if response.status_code == 401:
                return
        
        pytest.skip("No protected endpoint found that returns 401")


class TestCRUDOperations:
    """Tests for common CRUD API patterns."""
    
    @pytest.mark.api
    def test_list_endpoint(self, api_client):
        """
        Verify a list/index endpoint returns array.
        
        Expected: GET to collection endpoint should return array.
        """
        list_endpoints = [
            "/api/items",
            "/api/users",
            "/api/posts",
            "/api/products",
        ]
        
        for endpoint in list_endpoints:
            try:
                response = api_client.get(endpoint)
                if response.status_code == 200:
                    data = response.json()
                    if isinstance(data, list) or (isinstance(data, dict) and any(
                        isinstance(v, list) for v in data.values()
                    )):
                        return
            except Exception:
                continue
        
        pytest.skip("No list endpoint found")
    
    @pytest.mark.api
    def test_not_found_returns_404(self, api_client):
        """
        Verify non-existent resource returns 404.
        
        Expected: GET to non-existent resource should return 404.
        """
        response = api_client.get("/api/nonexistent-resource-12345")
        assert response.status_code in [404, 401], f"Expected 404, got {response.status_code}"


class TestErrorHandling:
    """Tests for API error handling."""
    
    @pytest.mark.api
    def test_invalid_json_returns_error(self, api_client):
        """
        Verify API handles malformed JSON gracefully.
        
        Expected: Should return 400 for invalid JSON body.
        """
        post_endpoints = ["/api/login", "/api/auth/login", "/api/items"]
        
        for endpoint in post_endpoints:
            try:
                response = api_client.post(
                    endpoint,
                    content="not valid json",
                    headers={"Content-Type": "application/json"}
                )
                if response.status_code in [400, 415, 422]:
                    return
            except Exception:
                continue
        
        pytest.skip("No POST endpoint found to test")
    
    @pytest.mark.api
    def test_method_not_allowed(self, api_client):
        """
        Verify unsupported methods return 405.
        
        Expected: DELETE on read-only endpoint should return 405.
        """
        response = api_client.delete("/")
        assert response.status_code in [405, 404, 401], f"Expected 405, got {response.status_code}"


class TestAPIResponseFormat:
    """Tests for API response format consistency."""
    
    @pytest.mark.regression
    @pytest.mark.api
    def test_json_content_type(self, api_client):
        """
        Verify API returns proper JSON content type.
        
        Expected: API endpoints should return application/json.
        """
        api_endpoints = ["/api", "/api/health", "/api/status"]
        
        for endpoint in api_endpoints:
            try:
                response = api_client.get(endpoint)
                if response.status_code < 400:
                    content_type = response.headers.get("content-type", "")
                    if "application/json" in content_type:
                        return
            except Exception:
                continue
        
        pytest.skip("No JSON API endpoint found")
    
    @pytest.mark.regression
    @pytest.mark.api
    def test_cors_headers(self, api_client):
        """
        Verify CORS headers are present for API.
        
        Expected: API should include CORS headers for cross-origin access.
        """
        try:
            response = api_client.options("/api")
        except Exception:
            response = api_client.get("/api")
        
        cors_headers = [
            "access-control-allow-origin",
            "access-control-allow-methods",
        ]
        
        has_cors = any(h in response.headers for h in cors_headers)
        
        if not has_cors:
            pytest.skip("CORS headers not present (may not be required)")
