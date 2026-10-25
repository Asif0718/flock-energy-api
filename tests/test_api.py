import json
from pathlib import Path
from urllib.parse import parse_qs

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

FIXTURES = Path(__file__).parent / "fixtures"
SETTINGS = Settings(base_url="https://portal.test", email="test@example.test", password="test-only")


def fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class Portal:
    def __init__(self):
        self.logins = 0
        self.expire = False
        self.always_expire = False
        self.failure = None
        self.bad_login = False
        self.cookie_seen = False

    def __call__(self, request):
        path = request.url.path
        if path == "/login":
            self.logins += 1
            assert request.method == "POST"
            assert parse_qs(request.content.decode()) == {"email": [SETTINGS.email], "password": [SETTINGS.password]}
            assert request.headers["x-sveltekit-action"] == "true"
            return httpx.Response(200, json={"type": "failure"} if self.bad_login else
                                  {"type": "redirect", "status": 303, "location": "/meters"},
                                  headers={"set-cookie": "test_session=fixture; Path=/; Secure; HttpOnly"})
        self.cookie_seen = "test_session=fixture" in request.headers.get("cookie", "")
        assert self.cookie_seen
        if path == "/portal/meters/search":
            return httpx.Response(200, json=fixture("meters.json"))
        if self.expire or self.always_expire:
            self.expire = False
            return httpx.Response(303, headers={"location": "/login"})
        if self.failure:
            return self.failure(request)
        if path == "/meters/J100004/__data.json":
            return httpx.Response(200, json=fixture("detail_classdata.json"))
        if path == "/meters/J100000/__data.json":
            assert request.url.params["x-sveltekit-invalidated"] == "001"
            return httpx.Response(200, json=fixture("detail.json"))
        if path == "/portal/meters/J100000/energy":
            return httpx.Response(200, json=fixture("energy.json"))
        return httpx.Response(404)


def api(portal):
    return TestClient(create_app(SETTINGS, httpx.MockTransport(portal)))


def test_login_cookie_persistence_and_captured_responses():
    upstream = Portal()
    with api(upstream) as client:
        listing = client.get("/api/v1/meters?q=J100000&page=1")
        assert listing.status_code == 200
        assert listing.json()["page_size"] == 20
        assert listing.json()["data"][0]["serial_number"] == "SE33962"
        detail = client.get("/api/v1/meters/J100000")
        assert detail.status_code == 200
        assert detail.json()["installation_type"] == "Whole Current"
        assert detail.json()["hierarchy"]["Zone"] == "Jaipur Zone 1 (Z-01)"
        readings = client.get("/api/v1/meters/J100000/consumption").json()["readings"]
        assert readings[0]["timestamp"] == "2026-06-23T23:30:00"
        assert readings[0]["kwh"] == 48438.74
        assert readings[0]["voltage_r"] == 226.0
        assert upstream.logins == 1 and upstream.cookie_seen


def test_expiration_reauthenticates_once():
    upstream = Portal()
    with api(upstream) as client:
        client.get("/api/v1/meters")
        upstream.expire = True
        assert client.get("/api/v1/meters/J100000").status_code == 200
        assert upstream.logins == 2
        upstream.always_expire = True
        assert client.get("/api/v1/meters/J100000").status_code == 502
        assert upstream.logins == 3


def test_captured_classdata_detail():
    with api(Portal()) as client:
        response = client.get("/api/v1/meters/J100004")
        assert response.status_code == 200
        body = response.json()
        assert body["meter_id"] == "J100004"
        assert body["serial_number"] == "SE65293"
        assert body["make"] == "Genus"
        assert body["installation_type"] == "CT Operated"
        assert body["installation_status"] == "Faulty"
        assert body["hierarchy"]["Zone"] == "Jaipur Zone 2 (Z-02)"


@pytest.mark.parametrize("classdata", ["invalid JSON", "{}", '{"installed_meter":null}',
                                      '{"installed_meter":{"MeterId":"J100000"}}'])
def test_invalid_classdata_fails_safely(classdata):
    body = fixture("detail_classdata.json")
    body["nodes"][2]["data"][3] = classdata
    upstream = Portal()
    upstream.failure = lambda request: httpx.Response(200, json=body)
    with api(upstream) as client:
        assert client.get("/api/v1/meters/J100004").status_code == 502


def test_http_200_is_not_authentication_success():
    upstream = Portal()
    upstream.bad_login = True
    with api(upstream) as client:
        response = client.get("/api/v1/meters")
        assert response.status_code == 502
        assert response.json() == {"detail": "Portal authentication failed"}


@pytest.mark.parametrize("status,expected", [(404, 404), (403, 502), (500, 502), (429, 502)])
def test_upstream_status_mapping(status, expected):
    upstream = Portal()
    upstream.failure = lambda request: httpx.Response(status, text="private upstream error")
    with api(upstream) as client:
        response = client.get("/api/v1/meters/J100000")
        assert response.status_code == expected
        assert "private" not in response.text


@pytest.mark.parametrize("error,status", [(httpx.ReadTimeout, 504), (httpx.ConnectError, 502)])
def test_transport_errors(error, status):
    upstream = Portal()
    def fail(request):
        raise error("secret transport detail", request=request)
    upstream.failure = fail
    with api(upstream) as client:
        response = client.get("/api/v1/meters/J100000")
        assert response.status_code == status
        assert "secret" not in response.text


@pytest.mark.parametrize("response", [
    httpx.Response(200, text="<html>Login</html>", headers={"content-type": "text/html"}),
    httpx.Response(200, text="not json", headers={"content-type": "application/json"}),
    httpx.Response(200, json={"nodes": []}),
])
def test_unexpected_responses(response):
    upstream = Portal()
    upstream.failure = lambda request: response
    with api(upstream) as client:
        assert client.get("/api/v1/meters/J100000").status_code == 502


def test_normalization():
    from app.models import EnergyReading, Meter
    meter = Meter.model_validate({"meterId": " J100000 ", "serialNo": " n/a ", "make": " L&T  ",
                                  "phaseType": "single", "installStatus": " Installed "})
    assert meter.serial_number is None and meter.make == "L&T"
    reading = EnergyReading.model_validate({"timestamp": "24/06/2026 00:00", "kwh": " - ", "kvah": " 12.50 ", "voltR": "230"})
    assert reading.kwh is None and reading.kvah == 12.5
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        EnergyReading.model_validate({"timestamp": "invalid", "kwh": "NaN", "kvah": "1", "voltR": "1"})


@pytest.mark.parametrize("name,meter_id", [("detail.json", "J100000"), ("detail_classdata.json", "J100004")])
def test_omitted_nullable_detail_fields(name, meter_id):
    body = fixture(name)
    values = body["nodes"][2]["data"]
    if name == "detail.json":
        # Keep just the captured Meter ID pair; omitted descriptive fields become null.
        values[3] = values[3][:1]
    else:
        values[3] = json.dumps({"installed_meter": {"MeterId": meter_id}})
    upstream = Portal()
    upstream.failure = lambda request: httpx.Response(200, json=body)
    with api(upstream) as client:
        response = client.get(f"/api/v1/meters/{meter_id}")
        assert response.status_code == 200
        assert response.json()["serial_number"] is None
        assert response.json()["installation_type"] is None


def test_omitted_nullable_search_and_energy_fields():
    from app.models import Meter, EnergyReading
    assert Meter.model_validate({"meterId": "J100004"}).serial_number is None
    assert EnergyReading.model_validate({"timestamp": "24/06/2026 00:00"}).kwh is None


def test_complete_but_mismatched_embedded_meter_id_is_rejected():
    body = fixture("detail_classdata.json")
    values = body["nodes"][2]["data"]
    installed = json.loads(values[3])
    installed["installed_meter"]["MeterId"] = "J100000"
    values[3] = json.dumps(installed)
    upstream = Portal()
    upstream.failure = lambda request: httpx.Response(200, json=body)
    with api(upstream) as client:
        assert client.get("/api/v1/meters/J100004").status_code == 502


def test_invalid_inputs_and_missing_credentials():
    with api(Portal()) as client:
        assert client.get("/api/v1/meters?page=0").status_code == 422
        assert client.get("/api/v1/meters/bad.id").status_code == 422
    with TestClient(create_app(Settings())) as client:
        assert client.get("/api/v1/meters").status_code == 503


def test_cleanup_and_openapi_matches_export():
    application = create_app(SETTINGS, httpx.MockTransport(Portal()))
    with TestClient(application) as client:
        assert client.get("/docs").status_code == 200
        assert client.get("/openapi.json").status_code == 200
    assert application.state.portal.http.is_closed
    assert application.openapi() == json.loads(Path("openapi.json").read_text(encoding="utf-8"))
