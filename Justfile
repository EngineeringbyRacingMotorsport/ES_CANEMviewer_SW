[windows]
set shell := ["powershell.exe", "-NoLogo", "-Command"]

[windows]
EXE_EXTENSION := ".exe"
[unix]
EXE_EXTENSION := ""

[windows]
VENV_SCRIPTS := ".venv" / "Scripts"
[unix]
VENV_SCRIPTS := ".venv" / "bin"

PIP_PATH := VENV_SCRIPTS / ("pip" + EXE_EXTENSION)
PYTHON_PATH := VENV_SCRIPTS / ("python" + EXE_EXTENSION)

venv:
    python3 -m venv --system-site-packages .venv
    {{ PIP_PATH }} install -r requirements.txt
    # Tk 8.7+ renders SVGs itself; older versions need tksvg
    {{ PYTHON_PATH }} -c "import subprocess, sys, tkinter; tkinter.TkVersion < 8.7 and subprocess.check_call([sys.executable, '-m', 'pip', 'install', '-r', 'requirements-tk86.txt'])"

run:
    {{ PYTHON_PATH }} -m src.main

gen-example:
    {{ PYTHON_PATH }} -m tools.gen_example

gen-schema:
    {{ PYTHON_PATH }} -m tools.gen_schema
