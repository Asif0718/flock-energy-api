from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, BeforeValidator


def clean(value):
    if isinstance(value, str):
        value = " ".join(value.split())
        if value.lower() in ("", "n/a", "null", "none", "-"):
            return None
    return value


Text = Annotated[str | None, BeforeValidator(clean)]
Number = Annotated[Annotated[float, Field(allow_inf_nan=False)] | None, BeforeValidator(clean)]


class PortalModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


class Meter(PortalModel):
    meter_id: Annotated[str, BeforeValidator(clean)] = Field(validation_alias="meterId", min_length=1)
    serial_number: Text = Field(default=None, validation_alias="serialNo")
    make: Text = None
    phase_type: Text = Field(default=None, validation_alias="phaseType")
    installation_status: Text = Field(default=None, validation_alias="installStatus")
    dt_code: Text = Field(default=None, validation_alias="dtCode")


class MeterPage(BaseModel):
    data: list[Meter]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(validation_alias="pageSize", gt=0)


class MeterDetail(Meter):
    installation_type: Text = None
    hierarchy: dict[str, Text]


def parse_timestamp(value):
    if isinstance(value, str):
        return datetime.strptime(" ".join(value.split()), "%d/%m/%Y %H:%M")
    return value


class EnergyReading(PortalModel):
    timestamp: Annotated[datetime, BeforeValidator(parse_timestamp)]
    kwh: Number = None
    kvah: Number = None
    voltage_r: Number = Field(default=None, validation_alias="voltR")


class Consumption(BaseModel):
    meter_id: str
    readings: list[EnergyReading]


class ErrorResponse(BaseModel):
    detail: str
