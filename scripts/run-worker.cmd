@echo off
setlocal

set "MODE=run"

:parse_args
if "%~1"=="" goto run_worker
if /I "%~1"=="--help" goto print_help
if /I "%~1"=="-h" goto print_help
if /I "%~1"=="--once" (
    set "MODE=once"
    shift
    goto parse_args
)
if /I "%~1"=="--run" (
    set "MODE=run"
    shift
    goto parse_args
)

echo Unknown option: %~1 1>&2
echo Run scripts\run-worker.cmd --help for usage. 1>&2
exit /b 2

:run_worker
pushd "%~dp0" || exit /b 1
if not exist "pyproject.toml" (
    if exist "..\pyproject.toml" (
        cd ..
    ) else (
        echo Could not find repository root. 1>&2
        popd
        exit /b 1
    )
)

set "PYTHON=%CD%\.venv\Scripts\python.exe"
if not exist "%PYTHON%" (
    echo Missing virtual environment: %PYTHON% 1>&2
    echo Run: uv sync --group dev --group docs --extra api --extra streamlit --extra worker --link-mode=copy 1>&2
    popd
    exit /b 1
)

if defined PYTHONPATH (
    set "PYTHONPATH=%CD%\backend\src;%PYTHONPATH%"
) else (
    set "PYTHONPATH=%CD%\backend\src"
)
if not defined WEREWOLF_LOG_FILE_NAME (
    set "WEREWOLF_LOG_FILE_NAME=worker.jsonl"
)

"%PYTHON%" -m werewolf_agent.interface.entrypoint.worker.app %MODE%
set "EXIT_CODE=%ERRORLEVEL%"

popd
exit /b %EXIT_CODE%

:print_help
echo Usage: scripts\run-worker.cmd [--run^|--once]
echo.
echo Runs the Supabase request queue worker.
echo Required secret: WEREWOLF_SUPABASE_DB_DSN.
echo Operational logs default to .werewolf-agent\logs\worker.jsonl.
exit /b 0
