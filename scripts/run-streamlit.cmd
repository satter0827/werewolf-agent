@echo off
setlocal

set "PORT=8501"

if /I "%~1"=="--help" goto print_help
if /I "%~1"=="-h" goto print_help
if not "%~1"=="" (
    echo Unknown option: %~1 1>&2
    echo Run scripts\run-streamlit.cmd --help for usage. 1>&2
    exit /b 2
)

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
    echo Run: uv sync --group dev --group docs --extra streamlit --extra worker --link-mode=copy 1>&2
    popd
    exit /b 1
)

for /f "tokens=5" %%P in ('netstat -ano -p tcp ^| findstr /R /C:":%PORT% .*LISTENING"') do (
    set "PORT_PID=%%P"
)
if defined PORT_PID (
    echo Port %PORT% is already in use by PID %PORT_PID%. 1>&2
    tasklist /FI "PID eq %PORT_PID%" /FO LIST 2>nul | findstr /B /C:"Image Name" /C:"PID" 1>&2
    popd
    exit /b 1
)

if defined PYTHONPATH (
    set "PYTHONPATH=%CD%\backend\src;%PYTHONPATH%"
) else (
    set "PYTHONPATH=%CD%\backend\src"
)
if not defined WEREWOLF_LOG_FILE_NAME (
    set "WEREWOLF_LOG_FILE_NAME=streamlit.jsonl"
)

"%PYTHON%" -m streamlit run backend/src/werewolf_agent/entrypoint/streamlit/app.py --server.address 127.0.0.1 --server.port %PORT% --server.headless true --browser.gatherUsageStats false
set "EXIT_CODE=%ERRORLEVEL%"

popd
exit /b %EXIT_CODE%

:print_help
echo Usage: scripts\run-streamlit.cmd
echo.
echo Runs Streamlit on http://127.0.0.1:8501 with the project virtual environment.
echo Run scripts\preflight-supabase.cmd first when using the Supabase-only stack.
echo Operational logs default to .werewolf-agent\logs\streamlit.jsonl.
exit /b 0
