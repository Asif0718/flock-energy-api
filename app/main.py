from contextlib import asynccontextmanager
import logging
from typing import Annotated

from fastapi import Depends, FastAPI, Path, Query, Request
from fastapi.responses import JSONResponse

from app.client import PortalError, UrjaPortalClient
from app.config import Settings
from app.models import Consumption, ErrorResponse, MeterDetail, MeterPage

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None, transport=None):
    @asynccontextmanager
    async def lifespan(application):
        client = UrjaPortalClient(settings or Settings.from_env(), transport=transport)
        application.state.portal = client
        try:
            yield
        finally:
            await client.aclose()

    application = FastAPI(title="Flock Energy Urja API", version="1.0.0", lifespan=lifespan,
                          description="REST adapter for the captured Urja portal protocol. One configured operator identity per worker.")

    @application.exception_handler(PortalError)
    async def portal_error(request: Request, exc: PortalError):
        logger.warning("Portal request failed with wrapper status %s", exc.status)
        return JSONResponse(status_code=exc.status, content={"detail": exc.detail})

    def portal(request: Request):
        return request.app.state.portal

    client_dep = Annotated[UrjaPortalClient, Depends(portal)]
    meter_path = Annotated[str, Path(pattern=r"^[A-Za-z0-9_-]{1,64}$")]
    errors = {code: {"model": ErrorResponse} for code in (404, 502, 503, 504)}

    @application.get("/api/v1/meters", response_model=MeterPage, response_model_by_alias=False, responses=errors)
    async def meters(client: client_dep, q: str = Query(default="", max_length=200), page: int = Query(default=1, ge=1)):
        return await client.meters(q, page)

    @application.get("/api/v1/meters/{id}", response_model=MeterDetail, response_model_by_alias=False, responses=errors)
    async def meter(id: meter_path, client: client_dep):
        return await client.meter(id)

    @application.get("/api/v1/meters/{id}/consumption", response_model=Consumption, response_model_by_alias=False, responses=errors,
                     description="Returns cumulative energy readings, not interval consumption. Timestamps have no timezone in the source.")
    async def consumption(id: meter_path, client: client_dep):
        return await client.consumption(id)

    return application


app = create_app()
