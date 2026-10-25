"""Adapter for requests observed in portal.har; never forwards upstream bodies as errors."""
import asyncio
import json
import logging
from urllib.parse import quote, urlsplit

import httpx
from pydantic import ValidationError

from app.config import Settings
from app.models import Consumption, EnergyReading, MeterDetail, MeterPage, clean

logger = logging.getLogger(__name__)


class PortalError(Exception):
    def __init__(self, status: int, detail: str):
        self.status, self.detail = status, detail
        super().__init__(detail)


def decode_indexed(values: list, index: int = 0, active=None):
    """Decode the JSON-compatible subset of SvelteKit's captured devalue graph."""
    active = set() if active is None else active
    if type(index) is not int or index < 0 or index >= len(values) or index in active:
        raise ValueError("Unsupported indexed data reference")
    active = active | {index}
    value = values[index]
    if isinstance(value, dict):
        return {k: decode_indexed(values, v, active) for k, v in value.items()}
    if isinstance(value, list):
        return [decode_indexed(values, v, active) for v in value]
    return value


class UrjaPortalClient:
    def __init__(self, settings: Settings, transport=None):
        self.settings = settings
        self.http = httpx.AsyncClient(
            base_url=settings.base_url, timeout=httpx.Timeout(settings.timeout),
            follow_redirects=False, transport=transport,
        )
        # One configured service identity per worker; serialize cookie mutations and retries.
        self.lock = asyncio.Lock()
        self.authenticated = False

    async def aclose(self):
        await self.http.aclose()

    async def _send(self, method: str, path: str, **kwargs):
        try:
            return await self.http.request(method, path, **kwargs)
        except httpx.TimeoutException as exc:
            raise PortalError(504, "Portal request timed out") from exc
        except httpx.RequestError as exc:
            raise PortalError(502, "Could not connect to portal") from exc

    @staticmethod
    def _expired(response):
        return response.status_code == 401 or (
            response.is_redirect and urlsplit(response.headers.get("location", "")).path == "/login"
        )

    @staticmethod
    def _json(response):
        if response.status_code == 404:
            raise PortalError(404, "Meter or portal resource not found")
        if response.status_code == 403:
            raise PortalError(502, "Portal denied access")
        if response.status_code != 200:
            raise PortalError(502, "Portal returned an unsuccessful response")
        if "application/json" not in response.headers.get("content-type", ""):
            raise PortalError(502, "Portal returned an unexpected content type")
        try:
            result = response.json()
            if not isinstance(result, dict):
                raise ValueError()
            return result
        except ValueError as exc:
            raise PortalError(502, "Portal returned invalid JSON") from exc

    async def _login(self):
        self.authenticated = False
        self.http.cookies.clear()
        if not self.settings.email or not self.settings.password:
            raise PortalError(503, "Portal credentials are not configured")
        response = await self._send("POST", "/login", data={
            "email": self.settings.email, "password": self.settings.password,
        }, headers={"accept": "application/json", "x-sveltekit-action": "true",
                    "origin": self.settings.base_url, "referer": self.settings.base_url + "/login"})
        if response.status_code in (400, 401, 403):
            raise PortalError(502, "Portal authentication failed")
        body = self._json(response)
        if body.get("type") != "redirect" or body.get("status") != 303 or body.get("location") != "/meters":
            raise PortalError(502, "Portal authentication failed")
        # Verify a protected resource, not merely HTTP 200 or an action redirect.
        probe = await self._send("GET", "/portal/meters/search", params={"q": "", "page": 1})
        if self._expired(probe):
            raise PortalError(502, "Portal authentication failed")
        try:
            MeterPage.model_validate(self._json(probe))
        except ValidationError as exc:
            raise PortalError(502, "Portal authentication verification failed") from exc
        self.authenticated = True

    async def get_json(self, path, params=None):
        async with self.lock:
            if not self.authenticated:
                await self._login()
            response = await self._send("GET", path, params=params)
            if self._expired(response):
                self.authenticated = False
                logger.info("Portal session expired; reauthenticating once")
                await self._login()
                response = await self._send("GET", path, params=params)
                if self._expired(response):
                    self.authenticated = False
                    raise PortalError(502, "Portal authentication failed after retry")
            return self._json(response)

    async def meters(self, q: str, page: int):
        return await self._validated(MeterPage, "/portal/meters/search", {"q": q, "page": page})

    async def _validated(self, model, path, params=None):
        body = await self.get_json(path, params)
        try:
            return model.model_validate(body)
        except ValidationError as exc:
            raise PortalError(502, "Portal response did not match the expected schema") from exc

    async def meter(self, meter_id: str):
        body = await self.get_json(f"/meters/{quote(meter_id, safe='')}/__data.json",
                                   {"x-sveltekit-invalidated": "001"})
        try:
            node = body["nodes"][2]
            if body["type"] != "data" or node["type"] != "data":
                raise ValueError()
            decoded = decode_indexed(node["data"])
            if decoded["meterId"] != meter_id:
                raise ValueError()
            detail = decoded["detail"]
            if "classData" in detail:
                installed = json.loads(detail["classData"])["installed_meter"]
                if not isinstance(installed, dict):
                    raise ValueError()
                fields = {label: clean(installed.get(key)) for label, key in {
                    "Meter ID": "MeterId", "Serial No": "SerialNo", "Make": "Make",
                    "Phase Type": "PhaseType", "Installation Status": "InstallationStatus",
                    "Installation Type": "InstallationType",
                }.items()}
            else:
                fields = {clean(row["parameterName"]): clean(row["parameterValue"])
                          for row in detail["data"]}
            if fields["Meter ID"] != meter_id:
                raise ValueError()
            return MeterDetail.model_validate({
                "meter_id": meter_id, "serial_number": fields.get("Serial No"),
                "make": fields.get("Make"), "phase_type": fields.get("Phase Type"),
                "installation_status": fields.get("Installation Status"),
                "installation_type": fields.get("Installation Type"),
                "hierarchy": decoded["hierarchy"],
            })
        except (KeyError, IndexError, TypeError, ValueError, RecursionError) as exc:
            raise PortalError(502, "Portal meter detail schema was unexpected") from exc

    async def consumption(self, meter_id: str):
        body = await self.get_json(f"/portal/meters/{quote(meter_id, safe='')}/energy")
        try:
            if not isinstance(body["data"], list):
                raise ValueError()
            return Consumption(meter_id=meter_id, readings=[EnergyReading.model_validate(row) for row in body["data"]])
        except (KeyError, TypeError, ValueError) as exc:
            raise PortalError(502, "Portal energy schema was unexpected") from exc
