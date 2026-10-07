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
    {{ PYTHON_PATH }} -m venv --system-site-packages .venv
    {{ VENV_PIP_PATH }} install -r requirements.txt
    # Tk 8.7+ renders SVGs itself; older versions need tksvg
    {{ PYTHON_PATH }} -c "import subprocess, sys, tkinter; tkinter.TkVersion < 8.7 and subprocess.check_call([sys.executable, '-m', 'pip', 'install', '-r', 'requirements-tk86.txt'])"

run:
    {{ VENV_PYTHON_PATH }} -m src.main

gen-example:
    {{ VENV_PYTHON_PATH }} -m tools.gen_example

plot *ARGS:
    {{ VENV_PYTHON_PATH }} -m tools.plot {{ ARGS }}
