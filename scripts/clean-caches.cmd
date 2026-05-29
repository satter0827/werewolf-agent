@echo off
setlocal

set "APPLY=0"

:parse_args
if "%~1"=="" goto run_clean
if /I "%~1"=="--help" goto print_help
if /I "%~1"=="-h" goto print_help
if /I "%~1"=="--dry-run" (
    set "APPLY=0"
    shift
    goto parse_args
)
if /I "%~1"=="--apply" (
    set "APPLY=1"
    shift
    goto parse_args
)

echo Unknown option: %~1 1>&2
echo Run scripts\clean-caches.cmd --help for usage. 1>&2
exit /b 2

:run_clean
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

if "%APPLY%"=="1" (
    echo Removing local cache and documentation build artifacts.
) else (
    echo Dry run. Pass --apply to remove these paths.
)

call :clean_path ".werewolf-agent\cache\pytest"
call :clean_path ".werewolf-agent\cache\ruff"
call :clean_path ".werewolf-agent\cache\mypy"
call :clean_path ".werewolf-agent\cache\sphinx"
call :clean_path ".werewolf-agent\coverage"
call :clean_path "docs\sphinx\_build"
call :clean_path ".cache"
call :clean_path ".pytest_cache"
call :clean_path ".ruff_cache"
call :clean_path ".mypy_cache"
call :clean_path ".pytest-tmp"
call :clean_path ".coverage"
call :clean_path "coverage.xml"
call :clean_path "htmlcov"

popd
exit /b 0

:clean_path
set "TARGET=%~1"
if "%TARGET%"=="" exit /b 1
echo(%TARGET%| findstr /C:".." >nul
if not errorlevel 1 (
    echo Refusing path outside repository: %TARGET% 1>&2
    exit /b 1
)
echo(%TARGET%| findstr /R "^[A-Za-z]:" >nul
if not errorlevel 1 (
    echo Refusing absolute path: %TARGET% 1>&2
    exit /b 1
)
echo(%TARGET%| findstr /B "\\" >nul
if not errorlevel 1 (
    echo Refusing absolute path: %TARGET% 1>&2
    exit /b 1
)

dir /ad %TARGET% >nul 2>nul
if not errorlevel 1 goto clean_directory
if exist %TARGET% goto clean_file

echo Missing %TARGET%
exit /b 0

:clean_directory
if "%APPLY%"=="1" (
    echo Removing %TARGET%
    rmdir /s /q %TARGET%
) else (
    echo Would remove %TARGET%
)
exit /b 0

:clean_file
if "%APPLY%"=="1" (
    echo Removing %TARGET%
    del /f /q %TARGET%
) else (
    echo Would remove %TARGET%
)
exit /b 0

:print_help
echo Usage: scripts\clean-caches.cmd [--dry-run^|--apply]
echo.
echo Dry-run is the default. This script does not remove .werewolf-agent\db,
echo .werewolf-agent\logs, or .werewolf-agent\cache\uv.
exit /b 0
