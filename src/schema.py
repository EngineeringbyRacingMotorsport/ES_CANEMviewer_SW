import sqlite3
from .utils import quote_ident, read_text_file
from cantools.database import load_string
from cantools.database.can import Database, Node
from cantools.database.can import Message as CanMessage
from cantools.database.can import Signal as CanSignal
from cantools.database.can.formats.dbc import (
    DbcAttribute,
    DbcAttributeDefinition,
    DbcAttributeDefinitionType,
    DbcAttributeType,
    DbcSpecifics,
)
from cantools.database.conversion import BaseConversion
from collections import OrderedDict
from pydantic import BaseModel, ConfigDict, Field, model_validator
from typing import Annotated, Final, Literal

FORMAT_VERSION: Final = 1

Identifier = Annotated[str, Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")]
HexId = Annotated[str, Field(pattern=r"^0x[0-9A-Fa-f]+$")]
Number = int | float
AttributeMap = dict[str, int | float | str]
FrameFormatName = Literal["standard", "extended", "j1939"]


def _compact(value: Number) -> Number:
    """Integral floats as ints, so the DBC holds 0 instead of 0.0"""
    return int(value) if isinstance(value, float) and value.is_integer() else value


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LimitSet(_Model):
    """Alarm thresholds in physical units; null disables a limit"""

    CriticalLow: Number | None = None
    WarningLow: Number | None = None
    WarningHigh: Number | None = None
    CriticalHigh: Number | None = None

    @model_validator(mode="after")
    def _check_order(self) -> "LimitSet":
        limits = [
            limit
            for limit in (
                self.CriticalLow,
                self.WarningLow,
                self.WarningHigh,
                self.CriticalHigh,
            )
            if limit is not None
        ]
        if limits != sorted(limits):
            raise ValueError(
                "Limits must satisfy CriticalLow <= WarningLow <= WarningHigh <= CriticalHigh"
            )
        return self


class ModeLimits(_Model):
    i: LimitSet | None = None
    p: LimitSet | None = None
    t: LimitSet | None = None
    r: LimitSet | None = None


class ViewerInfo(_Model):
    """Data used by the viewer only, never written to the DBC"""

    Category: list[str] = Field(default_factory=list)
    Limits: ModeLimits = Field(default_factory=ModeLimits)


class Signal(_Model):
    StartBit: int = Field(ge=0)
    Length: int = Field(ge=1, le=64)
    ByteOrder: Literal["little_endian", "big_endian"] = "little_endian"
    Signed: bool = False
    Float: bool | None = None
    Factor: Number = 1
    Offset: Number = 0
    # Defaults to the full range representable by the signal
    Minimum: Number | None = None
    Maximum: Number | None = None
    Unit: str = ""
    Comment: str | None = None
    Receivers: list[str] = Field(default_factory=list)
    Multiplexer: bool = False
    MultiplexerIds: list[int] | None = None
    Choices: dict[int, str] | None = None
    Attributes: AttributeMap = Field(default_factory=dict)
    Viewer: ViewerInfo = Field(default_factory=ViewerInfo)

    @model_validator(mode="after")
    def _check_range(self) -> "Signal":
        minimum, maximum = self.physical_range()
        if minimum is not None and maximum is not None and minimum > maximum:
            raise ValueError("Minimum must not be greater than Maximum")
        return self

    def default_range(self) -> tuple[Number, Number] | None:
        """Physical range covered by every raw value of the signal"""
        if self.Float:
            return None
        if self.Signed:
            raw = (-(1 << (self.Length - 1)), (1 << (self.Length - 1)) - 1)
        else:
            raw = (0, (1 << self.Length) - 1)
        a, b = (_compact(value * self.Factor + self.Offset) for value in raw)
        return (min(a, b), max(a, b))

    def physical_range(self) -> tuple[Number | None, Number | None]:
        default_min, default_max = self.default_range() or (None, None)
        return (
            self.Minimum if self.Minimum is not None else default_min,
            self.Maximum if self.Maximum is not None else default_max,
        )


class Message(_Model):
    Id: HexId
    FrameFormat: FrameFormatName
    Length: int = Field(ge=0, le=64)
    Senders: list[str] = Field(default_factory=list)
    CycleTime: int | None = Field(default=None, ge=0)
    Comment: str | None = None
    Attributes: AttributeMap = Field(default_factory=dict)
    Signals: dict[Identifier, Signal]

    @property
    def frame_id(self) -> int:
        return int(self.Id, 16)

    @property
    def multiplexer(self) -> str | None:
        """Name of the signal selecting the multiplexed signals, if any"""
        return next(
            (name for name, signal in self.Signals.items() if signal.Multiplexer), None
        )

    @model_validator(mode="after")
    def _check(self) -> "Message":
        max_id = 0x7FF if self.FrameFormat == "standard" else 0x1FFF_FFFF
        if self.frame_id > max_id:
            raise ValueError(f"Id {self.Id} does not fit a {self.FrameFormat} frame")

        multiplexers = [
            name for name, signal in self.Signals.items() if signal.Multiplexer
        ]
        if len(multiplexers) > 1:
            raise ValueError(f"Multiple multiplexer signals: {', '.join(multiplexers)}")
        if not multiplexers and any(
            s.MultiplexerIds is not None for s in self.Signals.values()
        ):
            raise ValueError("MultiplexerIds used without a Multiplexer signal")
        return self


class Schema(_Model):
    model_config = ConfigDict(
        extra="forbid", validate_by_name=True, validate_by_alias=True
    )

    JsonSchema: str | None = Field(default=None, alias="$schema")
    FormatVersion: Literal[1]
    Version: str = ""
    Nodes: list[Identifier] = Field(default_factory=list)
    Attributes: AttributeMap = Field(default_factory=dict)
    Messages: dict[Identifier, Message]

    @model_validator(mode="after")
    def _check(self) -> "Schema":
        if len(set(self.Nodes)) != len(self.Nodes):
            raise ValueError("Nodes contains duplicates")

        nodes = set(self.Nodes)
        frames: dict[tuple[int, bool], str] = {}
        for name, message in self.Messages.items():
            unknown = set(message.Senders) - nodes
            for signal in message.Signals.values():
                unknown |= set(signal.Receivers) - nodes
            if unknown:
                raise ValueError(
                    f"Message {name} references unknown nodes: {', '.join(sorted(unknown))}"
                )

            frame = (message.frame_id, message.FrameFormat == "extended")
            if frame in frames:
                raise ValueError(
                    f"Messages {frames[frame]} and {name} share Id {message.Id}"
                )
            frames[frame] = name
        return self


_schema: tuple[str, Schema, Database, sqlite3.Connection] | None = None


def load(path: str) -> tuple[Schema, Database, sqlite3.Connection]:
    schema = Schema.model_validate_json(read_text_file(path))
    conn = _create_connection(schema)
    db = _create_database(schema)
    return (schema, db, conn)


def get_all(
    path: str | None = None,
) -> tuple[Schema, Database, sqlite3.Connection] | None:
    global _schema
    if path is not None:
        schema, can, conn = load(path)
        _schema = (path, schema, can, conn)
        return (schema, can, conn)
    elif _schema is not None:
        return (_schema[1], _schema[2], _schema[3])
    else:
        return None


def get_schema(path: str | None = None) -> Schema | None:
    schema = get_all(path)
    return schema[0] if schema is not None else None


def get_can(path: str | None = None) -> Database | None:
    schema = get_all(path)
    return schema[1] if schema is not None else None


def get_connection(path: str | None = None) -> sqlite3.Connection | None:
    schema = get_all(path)
    return schema[2] if schema is not None else None


TIMESTAMP_COLUMN: Final[str] = "__timestamp_"


def _column_type(signal: Signal) -> str:
    # Decoded value is raw * Factor + Offset, with an integral raw value
    if not signal.Float and signal.Factor.is_integer() and signal.Offset.is_integer():
        return "INTEGER"
    return "REAL"


# One table per message (named after it), with the reception time followed by
# one column per signal
def _create_connection(schema: Schema) -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    try:
        for name, message in schema.Messages.items():
            if TIMESTAMP_COLUMN in message.Signals:
                raise ValueError(
                    f"Signal name '{TIMESTAMP_COLUMN}' in message {name} is reserved"
                )

            columns = [f"{quote_ident(TIMESTAMP_COLUMN)} INTEGER NOT NULL"]
            for signal_name, signal in message.Signals.items():
                # Multiplexed signals are only present in some of the frames
                nullable = signal.MultiplexerIds is not None
                columns.append(
                    f"{quote_ident(signal_name)} {_column_type(signal)}{'' if nullable else ' NOT NULL'}"
                )
            conn.execute(f"CREATE TABLE {quote_ident(name)} ({', '.join(columns)})")
    except:
        conn.close()
        raise
    return conn


# Attribute definitions of the CANdb++ J1939 template every generated DBC is based on
_DBC_TEMPLATE: Final[str] = """VERSION ""
NS_ :
BS_:
BU_:
BA_DEF_ BO_  "VFrameFormat" ENUM  "StandardCAN","ExtendedCAN","reserved","reserved","reserved","reserved","reserved","reserved","reserved","reserved","reserved","reserved","reserved","reserved","StandardCAN_FD","ExtendedCAN_FD","J1939PGN";
BA_DEF_ BO_  "SendMode" ENUM  "Cyclic","IfActive","NoMsgSendType";
BA_DEF_ BO_  "VCAN_J1939_PGN" INT 0 262143;
BA_DEF_ BU_  "NodeAddress" INT 0 255;
BA_DEF_ BU_  "J1939AAC" INT 0 1;
BA_DEF_ BU_  "J1939IndustryGroup" INT 0 7;
BA_DEF_ BU_  "J1939System" INT 0 127;
BA_DEF_ BU_  "J1939SystemInstance" INT 0 15;
BA_DEF_ BU_  "J1939Function" INT 0 255;
BA_DEF_ BU_  "J1939FunctionInstance" INT 0 31;
BA_DEF_ BU_  "J1939ECUInstance" INT 0 7;
BA_DEF_ BU_  "J1939ManufacturerCode" INT 0 2047;
BA_DEF_  "MultiplexExtEnabled" ENUM  "No","Yes";
BA_DEF_  "BusType" STRING ;
BA_DEF_DEF_  "VFrameFormat" "J1939PGN";
BA_DEF_DEF_  "SendMode" "Cyclic";
BA_DEF_DEF_  "VCAN_J1939_PGN" 0;
BA_DEF_DEF_  "NodeAddress" 254;
BA_DEF_DEF_  "J1939AAC" 0;
BA_DEF_DEF_  "J1939IndustryGroup" 0;
BA_DEF_DEF_  "J1939System" 0;
BA_DEF_DEF_  "J1939SystemInstance" 0;
BA_DEF_DEF_  "J1939Function" 0;
BA_DEF_DEF_  "J1939FunctionInstance" 0;
BA_DEF_DEF_  "J1939ECUInstance" 0;
BA_DEF_DEF_  "J1939ManufacturerCode" 0;
BA_DEF_DEF_  "MultiplexExtEnabled" "Yes";
BA_DEF_DEF_  "BusType" "J1939";
"""


def template_attribute_definitions() -> OrderedDict[str, DbcAttributeDefinitionType]:
    # Parsed on every call, since the DBC writer adds definitions to it
    database = load_string(_DBC_TEMPLATE, database_format="dbc")
    assert isinstance(database, Database) and database.dbc is not None
    return database.dbc.attribute_definitions


def _to_attributes(
    values: AttributeMap,
    kind: str | None,
    definitions: OrderedDict[str, DbcAttributeDefinitionType],
) -> OrderedDict[str, DbcAttributeType]:
    attributes: OrderedDict[str, DbcAttributeType] = OrderedDict()
    for name, value in values.items():
        definition = definitions.get(name)
        if definition is None:
            # Not part of the template, so infer its type from the value
            type_name = (
                "STRING"
                if isinstance(value, str)
                else "INT"
                if isinstance(value, int)
                else "FLOAT"
            )
            bounds = (None, None) if type_name == "STRING" else (0, 0)
            definition = DbcAttributeDefinition(name, None, kind, type_name, *bounds)
            definitions[name] = definition
        elif definition.kind != kind:
            raise ValueError(
                f"Attribute '{name}' is not defined for {kind or 'the database'}"
            )

        if definition.type_name == "ENUM":
            if value not in definition.choices:
                raise ValueError(
                    f"Attribute '{name}' must be one of {definition.choices}"
                )
            value = definition.choices.index(str(value))
        attributes[name] = DbcAttribute(value, definition)
    return attributes


def _to_signal(
    name: str,
    signal: Signal,
    multiplexer: str | None,
    definitions: OrderedDict[str, DbcAttributeDefinitionType],
) -> CanSignal:
    minimum, maximum = signal.physical_range()
    initial = signal.Attributes.get("GenSigStartValue")
    return CanSignal(
        name=name,
        start=signal.StartBit,
        length=signal.Length,
        byte_order=signal.ByteOrder,
        is_signed=signal.Signed,
        raw_initial=float(initial) if initial is not None else None,
        conversion=BaseConversion.factory(
            scale=signal.Factor,
            offset=signal.Offset,
            choices=dict(signal.Choices) if signal.Choices else None,
            is_float=bool(signal.Float),
        ),
        minimum=minimum,
        maximum=maximum,
        unit=signal.Unit or None,
        comment=signal.Comment,
        receivers=list(signal.Receivers),
        is_multiplexer=signal.Multiplexer,
        multiplexer_ids=signal.MultiplexerIds,
        multiplexer_signal=multiplexer if signal.MultiplexerIds is not None else None,
        dbc_specifics=DbcSpecifics(
            attributes=_to_attributes(signal.Attributes, "SG_", definitions)
        ),
    )


def _to_message(
    name: str,
    message: Message,
    definitions: OrderedDict[str, DbcAttributeDefinitionType],
) -> CanMessage:
    multiplexer = message.multiplexer
    return CanMessage(
        frame_id=message.frame_id,
        name=name,
        length=message.Length,
        signals=[
            _to_signal(n, s, multiplexer, definitions)
            for n, s in message.Signals.items()
        ],
        comment=message.Comment,
        senders=list(message.Senders),
        cycle_time=message.CycleTime,
        dbc_specifics=DbcSpecifics(
            attributes=_to_attributes(message.Attributes, "BO_", definitions)
        ),
        # J1939 frames are 29-bit, except for the 11-bit IDs the template allows
        is_extended_frame=message.FrameFormat == "extended"
        or (message.FrameFormat == "j1939" and message.frame_id > 0x7FF),
        # The writer omits VFrameFormat for j1939 messages, since cantools calls
        # it "J1939PG" and the template "J1939PGN", which leaves them at the
        # template's default of J1939PGN
        protocol="j1939" if message.FrameFormat == "j1939" else None,
        # Signals must stay sorted by start bit: cantools encodes unsorted ones wrongly
    )


def _create_database(schema: Schema) -> Database:
    """Builds the CAN database described by a parsed signal metadata file"""
    definitions = template_attribute_definitions()
    messages = [
        _to_message(name, message, definitions)
        for name, message in schema.Messages.items()
    ]
    return Database(
        messages=messages,
        nodes=[Node(name) for name in schema.Nodes],
        version=schema.Version,
        dbc_specifics=DbcSpecifics(
            attributes=_to_attributes(schema.Attributes, None, definitions),
            attribute_definitions=definitions,
        ),
    )
