#!/usr/bin/env bash
#
# Bash version of the Justfile, for machines without just.
#
# Usage, from any folder:
#     ./tasks.sh venv
#     ./tasks.sh run
#     ./tasks.sh gen-example
#     ./tasks.sh plot [json_path] [data_path]

set -euo pipefail

recipe="${1:-}"
shift || true

case "$(uname -s)" in
    MINGW* | MSYS* | CYGWIN*)
        python="python"
        venv_python=".venv/Scripts/python.exe"
        venv_pip=".venv/Scripts/pip.exe"
        ;;
    *)
        python="python3"
        venv_python=".venv/bin/python"
        venv_pip=".venv/bin/pip"
        ;;
esac

# Recipes run from the project root, like they do with just
cd "$(dirname "${BASH_SOURCE[0]}")"

case "$recipe" in
    venv)
        "$python" -m venv --system-site-packages .venv
        "$venv_pip" install -r requirements.txt
        # Tk 8.7+ renders SVGs itself; older versions need tksvg
        "$venv_python" -c "import subprocess, sys, tkinter; tkinter.TkVersion < 8.7 and subprocess.check_call([sys.executable, '-m', 'pip', 'install', '-r', 'requirements-tk86.txt'])"
        ;;
    run)
        "$venv_python" -m src.main
        ;;
    gen-example)
        "$venv_python" -m tools.gen_example
        ;;
    plot)
        "$venv_python" -m tools.plot "$@"
        ;;
    *)
        echo "Unknown recipe '$recipe'. Available recipes: venv, run, gen-example, plot" >&2
        exit 1
        ;;
esac
