"""Tests for OpenAPI spec and Swagger UI endpoints."""


class TestOpenApiSpec:
    def test_openapi_json_returns_200(self, client):
        resp = client.get("/openapi.json")
        assert resp.status_code == 200

    def test_openapi_json_is_valid_spec(self, client):
        spec = client.get("/openapi.json").get_json()
        assert spec["openapi"].startswith("3.")
        assert "info" in spec
        assert "paths" in spec

    def test_openapi_contains_customer_paths(self, client):
        spec = client.get("/openapi.json").get_json()
        assert "/customers" in spec["paths"]
        assert "/customers/{customer_id}" in spec["paths"]

    def test_openapi_contains_vehicle_paths(self, client):
        spec = client.get("/openapi.json").get_json()
        assert "/vehicles" in spec["paths"]
        assert "/vehicles/{identifier}" in spec["paths"]

    def test_openapi_contains_appointment_paths(self, client):
        spec = client.get("/openapi.json").get_json()
        assert "/appointments" in spec["paths"]

    def test_openapi_contains_all_components(self, client):
        spec = client.get("/openapi.json").get_json()
        schemas = spec["components"]["schemas"]
        for name in ("Customer", "CustomerCreate", "Vehicle", "Appointment"):
            assert name in schemas, f"Schema '{name}' missing from spec"


class TestSwaggerUI:
    def test_swagger_ui_returns_200(self, client):
        resp = client.get("/swagger-ui")
        assert resp.status_code == 200

    def test_swagger_ui_returns_html(self, client):
        resp = client.get("/swagger-ui")
        assert b"swagger-ui" in resp.data.lower()

    def test_swagger_ui_references_openapi_json(self, client):
        resp = client.get("/swagger-ui")
        assert b"/openapi.json" in resp.data

    def test_swagger_ui_trailing_slash_works(self, client):
        resp = client.get("/swagger-ui/")
        assert resp.status_code == 200
