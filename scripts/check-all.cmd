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
    echo Run: uv sync --group dev --extra api 1>&2
    popd
    exit /b 1
)

if defined PYTHONPATH (
    set "PYTHONPATH=%CD%\backend\src;%PYTHONPATH%"
) else (
    set "PYTHONPATH=%CD%\backend\src"
)

echo.
echo === doctor ===
"%PYTHON%" -m werewolf_agent doctor --output json
call :check_status %ERRORLEVEL%
if errorlevel 1 goto finish

echo.
echo === pytest ===
"%PYTHON%" -m pytest
call :check_status %ERRORLEVEL%
if errorlevel 1 goto finish

echo.
echo === ruff check ===
"%PYTHON%" -m ruff check .
call :check_status %ERRORLEVEL%
if errorlevel 1 goto finish

echo.
echo === ruff format check ===
"%PYTHON%" -m ruff format --check .
call :check_status %ERRORLEVEL%
if errorlevel 1 goto finish

echo.
echo === mypy ===
"%PYTHON%" -m mypy backend/src
call :check_status %ERRORLEVEL%
if errorlevel 1 goto finish

if not "%RUN_API_CHECKS%"=="1" goto finish

echo.
echo === alembic upgrade head ===
"%PYTHON%" -m alembic upgrade head
call :check_status %ERRORLEVEL%
if errorlevel 1 goto finish

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
echo   --api         Also run Alembic migration and API integration tests.
echo   --keep-going  Continue after failed checks and exit non-zero at the end.
exit /b 0
