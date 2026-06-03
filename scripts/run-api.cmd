@echo off
setlocal

set "HOST=127.0.0.1"
set "PORT=8000"
set "RELOAD="

:parse_args
if "%~1"=="" goto run_api
if /I "%~1"=="--help" goto print_help
if /I "%~1"=="-h" goto print_help
if /I "%~1"=="--reload" (
    set "RELOAD=--reload"
    shift
    goto parse_args
)
if /I "%~1"=="--host" (
    if "%~2"=="" (
        echo Missing value for --host. 1>&2
        exit /b 2
    )
    set "HOST=%~2"
    shift
    shift
    goto parse_args
)
if /I "%~1"=="--port" (
    if "%~2"=="" (
        echo Missing value for --port. 1>&2
        exit /b 2
    )
    set "PORT=%~2"
    shift
    shift
    goto parse_args
)

echo Unknown option: %~1 1>&2
echo Run scripts\run-api.cmd --help for usage. 1>&2
exit /b 2

:run_api
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
    set "WEREWOLF_LOG_FILE_NAME=api.jsonl"
)

if defined RELOAD (
    "%PYTHON%" -m uvicorn werewolf_agent.interface.api.app:create_app --factory --host "%HOST%" --port "%PORT%" %RELOAD%
) else (
    "%PYTHON%" -m uvicorn werewolf_agent.interface.api.app:create_app --factory --host "%HOST%" --port "%PORT%"
)
set "EXIT_CODE=%ERRORLEVEL%"

popd
exit /b %EXIT_CODE%

:print_help
echo Usage: scripts\run-api.cmd [--host HOST] [--port PORT] [--reload]
echo.
echo Starts the minimal FastAPI health application with the local virtual environment.
echo Defaults: --host 127.0.0.1 --port 8000
echo Operational logs default to .werewolf-agent\logs\api.jsonl.
exit /b 0
