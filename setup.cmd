@echo off
rem One command to get a NIDS assignment running, on Windows.
rem
rem   setup.cmd --local            on your own machine, using public data
rem   setup.cmd --local --modules ASN,BGP
rem
rem A launcher, nothing more: every option is passed straight to
rem scripts\nids-setup.py setup, which is the same code setup.sh runs on
rem macOS and Linux. Run `setup.cmd --help` for the options.
setlocal

rem The py launcher ships with python.org installs and picks the newest Python;
rem `python` is the fallback for a PATH install or a conda environment.
where /q py.exe && (set "PY=py -3") || (set "PY=python")

%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" 2>nul
if errorlevel 1 (
    echo error: need Python 3.11 or newer on PATH.
    echo        Install it from https://www.python.org/downloads/windows/
    echo        and tick "Add python.exe to PATH" in the installer.
    exit /b 1
)

%PY% "%~dp0scripts\nids-setup.py" setup %*
exit /b %errorlevel%
