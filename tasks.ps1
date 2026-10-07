<#
PowerShell version of the Justfile, for machines without just.

Usage, from any folder:
    .\tasks.ps1 venv
    .\tasks.ps1 run
    .\tasks.ps1 gen-example
    .\tasks.ps1 plot [json_path] [data_path]
#>

# No [Parameter] attributes, so that arguments for the recipe (even ones starting
# with "-") end up in $args instead of being bound to this script
param([string] $Recipe)

$ErrorActionPreference = "Stop"
$RecipeArgs = $args

if ($env:OS -eq "Windows_NT") {
    $Python = "python"
    $VenvPython = Join-Path ".venv" "Scripts/python.exe"
    $VenvPip = Join-Path ".venv" "Scripts/pip.exe"
} else {
    $Python = "python3"
    $VenvPython = Join-Path ".venv" "bin/python"
    $VenvPip = Join-Path ".venv" "bin/pip"
}

# Runs a program, failing when it exits with an error like just does
function Invoke-Native {
    $command, $arguments = $args
    & $command @arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$command exited with code $LASTEXITCODE"
    }
}

# Recipes run from the project root, like they do with just
Push-Location $PSScriptRoot
try {
    switch ($Recipe) {
        "venv" {
            Invoke-Native $Python -m venv --system-site-packages .venv
            Invoke-Native $VenvPip install -r requirements.txt
            # Tk 8.7+ renders SVGs itself; older versions need tksvg
            Invoke-Native $VenvPython -c "import subprocess, sys, tkinter; tkinter.TkVersion < 8.7 and subprocess.check_call([sys.executable, '-m', 'pip', 'install', '-r', 'requirements-tk86.txt'])"
        }
        "run" {
            Invoke-Native $VenvPython -m src.main
        }
        "gen-example" {
            Invoke-Native $VenvPython -m tools.gen_example
        }
        "plot" {
            Invoke-Native $VenvPython -m tools.plot @RecipeArgs
        }
        default {
            throw "Unknown recipe '$Recipe'. Available recipes: venv, run, gen-example, plot"
        }
    }
} finally {
    Pop-Location
}
