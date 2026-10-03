from typing import Annotated
from pydantic import BaseModel, ConfigDict, Field, RootModel
from .utils import read_file

# [low critical, low warning, high warning, high critical]; -1 disables a limit
Limits = tuple[float, float, float, float]

MessageId = Annotated[str, Field(pattern=r"^[0-9A-Fa-f]+$")]


class Maximiters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    i: Limits
    p: Limits
    t: Limits
    r: Limits


class Signal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    Comment: str
    Unit: str
    Factor: float
    Offset: float
    Category: list[str]
    Maximiters: Maximiters


class Schema(RootModel[dict[str, dict[MessageId, dict[str, Signal]]]]):
    """Signals grouped by sending node, then by CAN frame ID string."""

def parse_schema(path: str) -> Schema:
    return Schema.model_validate_json(read_file(path))
