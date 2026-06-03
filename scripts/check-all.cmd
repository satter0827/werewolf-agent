@echo off
setlocal

set "RUN_API_CHECKS=0"
set "KEEP_GOING=0"
set "FAILED=0"

:parse_args
if "%~1"=="" goto run_checks
if /I "%~1"=="--help" goto print_help
if /I "%~1"=="-h" goto print_help
if /I "%~1"=="--api" (
    set "RUN_API_CHECKS=1"
    shift
    goto parse_args
)
if /I "%~1"=="--keep-going" (
    set "KEEP_GOING=1"
    shift
    goto parse_args
)

echo Unknown option: %~1 1>&2
echo Run scripts\check-all.cmd --help for usage. 1>&2
exit /b 2

:run_checks
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
    echo Run: uv sync --group dev --group docs --extra api --extra streamlit --link-mode=copy 1>&2
    popd
    exit /b 1
)

if defined PYTHONPATH (
    set "PYTHONPATH=%CD%\backend\src;%PYTHONPATH%"
) else (
    set "PYTHONPATH=%CD%\backend\src"
)
if not defined WEREWOLF_LOG_FILE_NAME (
    set "WEREWOLF_LOG_FILE_NAME=check-all.jsonl"
)

if not defined WEREWOLF_AGENT_RUNTIME_DIR (
    set "WEREWOLF_AGENT_RUNTIME_DIR=%TEMP%\werewolf-agent"
)
if not exist "%WEREWOLF_AGENT_RUNTIME_DIR%\cache\pytest" (
    mkdir "%WEREWOLF_AGENT_RUNTIME_DIR%\cache\pytest" >nul 2>nul
)
if not exist "%WEREWOLF_AGENT_RUNTIME_DIR%\cache\mypy" (
    mkdir "%WEREWOLF_AGENT_RUNTIME_DIR%\cache\mypy" >nul 2>nul
)

echo.
echo === doctor ===
"%PYTHON%" -m werewolf_agent doctor --output json
call :check_status %ERRORLEVEL%
if errorlevel 1 goto finish

echo.
echo === pytest ===
"%PYTHON%" -m pytest -o cache_dir="%WEREWOLF_AGENT_RUNTIME_DIR%\cache\pytest"
call :check_status %ERRORLEVEL%
if errorlevel 1 goto finish

echo.
echo === ruff check ===
"%PYTHON%" -m ruff check --no-cache .
call :check_status %ERRORLEVEL%
if errorlevel 1 goto finish

echo.
echo === ruff docstring check ===
"%PYTHON%" -m ruff check --no-cache --select D --ignore D100,D104 backend/src/werewolf_agent
call :check_status %ERRORLEVEL%
if errorlevel 1 goto finish

echo.
echo === ruff format check ===
"%PYTHON%" -m ruff format --check --no-cache .
call :check_status %ERRORLEVEL%
if errorlevel 1 goto finish

echo.
echo === mypy ===
"%PYTHON%" -m mypy --cache-dir "%WEREWOLF_AGENT_RUNTIME_DIR%\cache\mypy" backend/src
call :check_status %ERRORLEVEL%
if errorlevel 1 goto finish

if not "%RUN_API_CHECKS%"=="1" goto finish

echo.
echo === pytest tests/integration/api ===
"%PYTHON%" -m pytest tests/integration/api
call :check_status %ERRORLEVEL%
if errorlevel 1 goto finish

:finish
if "%FAILED%"=="1" (
    popd
    exit /b 1
)

set "EXIT_CODE=%ERRORLEVEL%"
popd
exit /b %EXIT_CODE%

:check_status
set "STATUS=%~1"
if "%STATUS%"=="0" exit /b 0

echo Command failed with exit code %STATUS%. 1>&2
if "%KEEP_GOING%"=="1" (
    set "FAILED=1"
    exit /b 0
)
exit /b %STATUS%

:print_help
echo Usage: scripts\check-all.cmd [--api] [--keep-going]
echo.
echo Runs local validation with .venv\Scripts\python.exe.
echo Runtime cache defaults to %%TEMP%%\werewolf-agent.
echo Operational logs default to .werewolf-agent\logs\check-all.jsonl.
echo   --api         Also run API integration tests.
echo   --keep-going  Continue after failed checks and exit non-zero at the end.
exit /b 0
