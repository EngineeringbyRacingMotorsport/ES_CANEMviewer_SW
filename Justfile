[windows]
set shell := ["powershell.exe", "-NoLogo", "-Command"]

[windows]
PYTHON_PATH := "python"
[unix]
PYTHON_PATH := "python3"

[windows]
EXE_EXTENSION := ".exe"
[unix]
EXE_EXTENSION := ""

[windows]
VENV_SCRIPTS := ".venv" / "Scripts"
[unix]
VENV_SCRIPTS := ".venv" / "bin"

VENV_PIP_PATH := VENV_SCRIPTS / ("pip" + EXE_EXTENSION)
VENV_PYTHON_PATH := VENV_SCRIPTS / ("python" + EXE_EXTENSION)

venv:
    {{ PYTHON_PATH }} -m venv .venv
    {{ VENV_PIP_PATH }} install -r requirements.txt

run:
    {{ VENV_PYTHON_PATH }} -m src.main

gen-example:
    {{ VENV_PYTHON_PATH }} -m tools.gen_example

dbc-to-json *ARGS:
    {{ VENV_PYTHON_PATH }} -m tools.dbc_to_json {{ ARGS }}
