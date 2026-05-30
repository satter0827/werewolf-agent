@echo off
setlocal

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
set "SPHINX_OUTPUT=docs\sphinx\_build\html"
set "SPHINX_BUILD_OUTPUT=%TEMP%\werewolf-agent-sphinx-html-%RANDOM%-%RANDOM%"
set "SPHINX_DOCTREES=%TEMP%\werewolf-agent-sphinx-doctrees-%RANDOM%-%RANDOM%"
set "SPHINX_FALLBACK=0"

if exist %SPHINX_OUTPUT% (
    > %SPHINX_OUTPUT%\.__write_test echo ok
    if errorlevel 1 (
        set "SPHINX_OUTPUT=docs\sphinx\_build\html-%RANDOM%-%RANDOM%"
        set "SPHINX_FALLBACK=1"
    ) else (
        del /f /q %SPHINX_OUTPUT%\.__write_test >nul 2>nul
    )
)

if not exist %SPHINX_OUTPUT%\searchindex.js goto output_ready
> %SPHINX_OUTPUT%\.__replace_test echo ok
move /y %SPHINX_OUTPUT%\.__replace_test %SPHINX_OUTPUT%\searchindex.js >nul 2>nul
if errorlevel 1 (
    del /f /q %SPHINX_OUTPUT%\.__replace_test >nul 2>nul
    set "SPHINX_OUTPUT=docs\sphinx\_build\html-%RANDOM%-%RANDOM%"
    set "SPHINX_FALLBACK=1"
)

:output_ready

if "%SPHINX_FALLBACK%"=="1" echo docs\sphinx\_build\html is not writable; using %SPHINX_OUTPUT%.

set "SPHINX_ARGS=-b html -c docs\sphinx -d %SPHINX_DOCTREES% docs %SPHINX_BUILD_OUTPUT%"

if exist "%PYTHON%" (
    "%PYTHON%" -c "import sphinx, myst_parser" >nul 2>nul
    if not errorlevel 1 (
        "%PYTHON%" -m sphinx %SPHINX_ARGS%
        set "EXIT_CODE=%ERRORLEVEL%"
        goto publish_output
    )
)

where uv >nul 2>nul
if errorlevel 1 (
    echo Sphinx is not installed in .venv and uv was not found on PATH. 1>&2
    echo Run: uv sync --group docs --extra api --extra streamlit 1>&2
    popd
    exit /b 1
)

uv run --group docs --extra api --extra streamlit sphinx-build %SPHINX_ARGS%
set "EXIT_CODE=%ERRORLEVEL%"

:publish_output
if not "%EXIT_CODE%"=="0" (
    popd
    exit /b %EXIT_CODE%
)

xcopy "%SPHINX_BUILD_OUTPUT%\*" "%SPHINX_OUTPUT%\" /E /I /Y >nul
if errorlevel 2 (
    echo Sphinx build succeeded, but copying HTML output failed. 1>&2
    echo Temporary HTML output: %SPHINX_BUILD_OUTPUT% 1>&2
    popd
    exit /b 1
)

rmdir /s /q "%SPHINX_BUILD_OUTPUT%" >nul 2>nul
rmdir /s /q "%SPHINX_DOCTREES%" >nul 2>nul
echo HTML pages are in %SPHINX_OUTPUT%.

popd
exit /b 0
