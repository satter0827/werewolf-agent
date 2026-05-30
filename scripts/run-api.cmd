@echo off
setlocal

set "MIGRATE=1"
set "HOST=127.0.0.1"
set "PORT=8000"
set "RELOAD="
set "TEMP_STATE=0"

:parse_args
if "%~1"=="" goto run_api
if /I "%~1"=="--help" goto print_help
if /I "%~1"=="-h" goto print_help
if /I "%~1"=="--no-migrate" (
    set "MIGRATE=0"
    shift
    goto parse_args
)
if /I "%~1"=="--reload" (
    set "RELOAD=--reload"
    shift
    goto parse_args
)
if /I "%~1"=="--temp-state" (
    set "TEMP_STATE=1"
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
    echo Run: uv sync --group dev --extra api 1>&2
    popd
    exit /b 1
)

if defined PYTHONPATH (
    set "PYTHONPATH=%CD%\backend\src;%PYTHONPATH%"
) else (
    set "PYTHONPATH=%CD%\backend\src"
)

if "%TEMP_STATE%"=="1" (
    if not defined WEREWOLF_AGENT_RUNTIME_DIR (
        set "WEREWOLF_AGENT_RUNTIME_DIR=%TEMP%\werewolf-agent"
    )
    if not exist "%WEREWOLF_AGENT_RUNTIME_DIR%\db" (
        mkdir "%WEREWOLF_AGENT_RUNTIME_DIR%\db" >nul 2>nul
    )
    if not defined WEREWOLF_SQLITE_PATH (
        set "WEREWOLF_SQLITE_PATH=%WEREWOLF_AGENT_RUNTIME_DIR%\db\api.sqlite3"
    )
)

if not "%MIGRATE%"=="1" goto start_server

"%PYTHON%" -m alembic upgrade head
if errorlevel 1 (
    popd
    exit /b 1
)

:start_server
if defined RELOAD (
    "%PYTHON%" -m uvicorn werewolf_agent.interface.api.app:create_app --factory --host "%HOST%" --port "%PORT%" %RELOAD%
) else (
    "%PYTHON%" -m uvicorn werewolf_agent.interface.api.app:create_app --factory --host "%HOST%" --port "%PORT%"
)
set "EXIT_CODE=%ERRORLEVEL%"

popd
exit /b %EXIT_CODE%

:print_help
echo Usage: scripts\run-api.cmd [--no-migrate] [--host HOST] [--port PORT] [--reload] [--temp-state]
echo.
echo Starts the FastAPI application with the local virtual environment.
echo Defaults: --host 127.0.0.1 --port 8000
echo   --temp-state  Use %%TEMP%%\werewolf-agent for SQLite.
exit /b 0
