COLORS = {
    "primary": "#0a594d",
    "bg_main": "#0f1a18",
    "bg_panel": "#132320",
    "text": "#f0f7f5",
    "ok": "#22c55e",
    "warning": "#facc15",
    "error": "#ef4444",
    "timeout": "#f97316",
    "muted": "#9eb7b2",
}

FONT_H1 = ("Segoe UI", 18, "bold")
FONT_H2 = ("Segoe UI", 14, "bold")
FONT_BODY = ("Segoe UI", 11)
FONT_VALUE = ("Segoe UI", 16, "bold")


def status_color(status: str) -> str:
    if status == "OK":
        return COLORS["ok"]
    if status == "WARNING":
        return COLORS["warning"]
    if status == "ERROR":
        return COLORS["error"]
    return COLORS["timeout"]
