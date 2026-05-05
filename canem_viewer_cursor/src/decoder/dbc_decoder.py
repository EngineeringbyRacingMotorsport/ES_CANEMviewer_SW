from __future__ import annotations

from typing import List, Tuple


class DBCDecoder:
    def __init__(self, dbc_path: str) -> None:
        self.dbc_path = dbc_path
        self.db = None
        self.available = False
        try:
            import cantools

            self.db = cantools.database.load_file(dbc_path)
            self.available = True
        except Exception:
            self.available = False

    def decode(self, arbitration_id: int, data: bytes) -> List[Tuple[str, str, float, str, str]]:
        if not self.available or self.db is None:
            return []
        try:
            msg_def = self.db.get_message_by_frame_id(arbitration_id)
            decoded = self.db.decode_message(arbitration_id, data)
        except Exception:
            return []

        output = []
        for sig_name, value in decoded.items():
            sig_def = next((s for s in msg_def.signals if s.name == sig_name), None)
            unit = sig_def.unit if sig_def else ""
            description = sig_def.comment if sig_def and sig_def.comment else ""
            output.append((msg_def.name, sig_name, float(value), unit or "", description or ""))
        return output
