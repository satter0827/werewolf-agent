@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "ROOT=%CD%"
set "DRYRUN=0"
set "FORCE=0"
set "INCLUDE_VENV=0"

for %%A in (%*) do (
  if /I "%%~A"=="/dryrun" set "DRYRUN=1"
  if /I "%%~A"=="/force" set "FORCE=1"
  if /I "%%~A"=="/include-venv" set "INCLUDE_VENV=1"
)

echo Target root: "%ROOT%"
if "%DRYRUN%"=="1" (
  echo Mode: DRY-RUN (no deletion)
) else (
  echo Mode: DELETE
)
if "%INCLUDE_VENV%"=="1" (
  echo Venv: INCLUDED
) else (
  echo Venv: EXCLUDED
)

REM ---- confirmation (robust) ----
if "%FORCE%"=="0" if "%DRYRUN%"=="0" (
  set "ANS="
  set /p "ANS=Proceed? (y/yes to continue): "
  set "ANS=!ANS: =!"
  if /I not "!ANS!"=="y" if /I not "!ANS!"=="yes" (
    echo Aborted.
    exit /b 1
  )
)

set "PS_WHATIF="
if "%DRYRUN%"=="1" set "PS_WHATIF=-WhatIf"

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Stop';" ^
  "$root = '%ROOT%';" ^
  "$includeVenv = [bool]([int]'%INCLUDE_VENV%');" ^
  "$venvRegex = '(\\\.venv\\|\\venv\\|\\env\\|\\ENV\\)';" ^
  "$cacheDirNames = @('__pycache__','.pytest_cache','.mypy_cache','.ruff_cache','.hypothesis','.tox','.nox','.pytype','.pyre','.pyright','.ipynb_checkpoints','htmlcov','build','dist','.eggs');" ^
  "Write-Host ('Root: ' + $root);" ^
  "function ShouldSkip([string]$path) { if ($includeVenv) { return $false } return ($path -match $venvRegex) }" ^
  "$dirs = Get-ChildItem -LiteralPath $root -Directory -Recurse -Force -ErrorAction SilentlyContinue | Where-Object { $cacheDirNames -contains $_.Name };" ^
  "$dirs = $dirs | Where-Object { -not (ShouldSkip $_.FullName) };" ^
  "foreach ($d in $dirs) { Write-Host ('Remove dir: ' + $d.FullName); Remove-Item -LiteralPath $d.FullName -Recurse -Force %PS_WHATIF% -ErrorAction SilentlyContinue }" ^
  "$filePatterns = @('*.pyc','*.pyo','*.pyd','.coverage','coverage.xml','*.coverage','*.cover','*.prof','*.log');" ^
  "foreach ($pat in $filePatterns) {" ^
  "  $files = Get-ChildItem -LiteralPath $root -File -Recurse -Force -Filter $pat -ErrorAction SilentlyContinue;" ^
  "  $files = $files | Where-Object { -not (ShouldSkip $_.FullName) };" ^
  "  foreach ($f in $files) { Write-Host ('Delete file: ' + $f.FullName); Remove-Item -LiteralPath $f.FullName -Force %PS_WHATIF% -ErrorAction SilentlyContinue }" ^
  "}" ^
  "$eggInfos = Get-ChildItem -LiteralPath $root -Directory -Recurse -Force -ErrorAction SilentlyContinue | Where-Object { $_.Name -like '*.egg-info' };" ^
  "$eggInfos = $eggInfos | Where-Object { -not (ShouldSkip $_.FullName) };" ^
  "foreach ($e in $eggInfos) { Write-Host ('Remove dir: ' + $e.FullName); Remove-Item -LiteralPath $e.FullName -Recurse -Force %PS_WHATIF% -ErrorAction SilentlyContinue }" ^
  "Write-Host 'Done.';"

exit /b %ERRORLEVEL%
