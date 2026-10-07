"""
Converts a DBC file into the signal metadata file format.

Run from the project root: python -m tools.dbc_to_json [dbc_path] [out_path]
"""

import math
import sys
from pathlib import Path

import cantools
from cantools.database.can import Database
from cantools.database.can import Message as CanMessage
from cantools.database.can import Signal as CanSignal
from cantools.database.can.formats.dbc import DbcSpecifics

from src.schema import (
    FORMAT_VERSION,
    AttributeMap,
    FrameFormatName,
    Message,
    Schema,
    Signal,
    template_attribute_definitions,
)

# Message attributes stored in their own fields
MESSAGE_FIELD_ATTRIBUTES = {"VFrameFormat", "GenMsgCycleTime"}


def warn(text: str) -> None:
    print(f"warning: {text}", file=sys.stderr)


def to_attribute_map(dbc: DbcSpecifics | None, skip: set[str] = set()) -> AttributeMap:
    if dbc is None:
        return {}
    values: AttributeMap = {}
    for name, attribute in dbc.attributes.items():
        if name in skip:
            continue
        definition = attribute.definition
        value = attribute.value
        # Enums are stored by their label, which is what the JSON file holds
        values[name] = definition.choices[int(value)] if definition.type_name == "ENUM" else value
    return values


def frame_format(db: Database, message: CanMessage) -> FrameFormatName:
    if message.is_fd:
        raise ValueError(f"Message {message.name}: CAN FD frames are not supported")

    label = None
    definition = db.dbc.attribute_definitions.get("VFrameFormat") if db.dbc else None
    if definition is not None and definition.type_name == "ENUM":
        attribute = message.dbc.attributes.get("VFrameFormat") if message.dbc else None
        label = definition.choices[int(attribute.value)] if attribute else definition.default_value

    if label in ("J1939PG", "J1939PGN"):
        return "j1939"
    return "extended" if message.is_extended_frame else "standard"


def to_signal(signal: CanSignal) -> Signal:
    result = Signal(
        StartBit=signal.start,
        Length=signal.length,
        ByteOrder=signal.byte_order,
        Signed=signal.is_signed,
        Float=True if signal.is_float else None,
        Factor=signal.scale,
        Offset=signal.offset,
        Unit=signal.unit or "",
        Comment=signal.comment or None,
        Receivers=list(signal.receivers),
        Multiplexer=signal.is_multiplexer,
        MultiplexerIds=signal.multiplexer_ids,
        Choices={int(k): str(v) for k, v in signal.choices.items()} if signal.choices else None,
        Attributes=to_attribute_map(signal.dbc),
    )

    # Only keep the limits narrower than what the signal can represent
    default_min, default_max = result.default_range() or (None, None)
    if signal.minimum is not None and (
        default_min is None or not math.isclose(signal.minimum, default_min, abs_tol=1e-9)
    ):
        result.Minimum = signal.minimum
    if signal.maximum is not None and (
        default_max is None or not math.isclose(signal.maximum, default_max, abs_tol=1e-9)
    ):
        result.Maximum = signal.maximum
    return result


def to_message(db: Database, message: CanMessage) -> Message:
    return Message(
        Id=f"0x{message.frame_id:X}",
        FrameFormat=frame_format(db, message),
        Length=message.length,
        Senders=list(message.senders),
        CycleTime=message.cycle_time,
        Comment=message.comment or None,
        Attributes=to_attribute_map(message.dbc, MESSAGE_FIELD_ATTRIBUTES),
        Signals={signal.name: to_signal(signal) for signal in message.signals},
    )


def from_database(db: Database) -> Schema:
    for node in db.nodes:
        if node.comment or (node.dbc and node.dbc.attributes):
            warn(f"comment and attributes of node {node.name} are not stored")

    if db.dbc is not None:
        template = template_attribute_definitions()
        for name in db.dbc.attribute_definitions:
            if name not in template and name not in MESSAGE_FIELD_ATTRIBUTES:
                warn(f"definition of attribute {name} is not stored, its type will be inferred")

    return Schema(
        FormatVersion=FORMAT_VERSION,
        Version=db.version or "",
        Nodes=[node.name for node in db.nodes],
        Attributes=to_attribute_map(db.dbc),
        Messages={message.name: to_message(db, message) for message in db.messages},
    )


def main(dbc_path: str, out_path: str) -> None:
    db = cantools.database.load_file(dbc_path, database_format="dbc", sort_signals=None)
    if not isinstance(db, Database):
        raise TypeError("Unsupported database type")

    schema = from_database(db)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(schema.model_dump_json(indent=2, by_alias=True, exclude_defaults=True))
        f.write("\n")

    print(f"Wrote {len(schema.Messages)} messages to {out_path}")


if __name__ == "__main__":
    dbc_path = sys.argv[1] if len(sys.argv) > 1 else "EMXCAN.dbc"
    main(dbc_path, sys.argv[2] if len(sys.argv) > 2 else str(Path(dbc_path).with_suffix(".json")))
