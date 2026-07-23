@echo off
setlocal

set "ROOT=%~dp0"
set "PYTHON_EXE=%ROOT%python\python.exe"
set "PORT=8420"

rem Isolate from any other Python this laptop may have installed. The embedded
rem interpreter's ._pth file already ignores these variables, verified against
rem a hostile PYTHONHOME and PYTHONPATH, but scrubbing them here makes the
rem isolation explicit and covers any dependency that reads them directly.
rem PYTHONUTF8 keeps output readable on a machine whose console codepage is not
rem UTF-8, which is most fresh Windows installs.
set "PYTHONHOME="
set "PYTHONPATH="
set "PYTHONSTARTUP="
set "PYTHONNOUSERSITE=1"
set "PYTHONUTF8=1"

if not exist "%PYTHON_EXE%" goto nopython

rem Find Microsoft Edge without assuming where Windows put it, so this runs on
rem any laptop regardless of the system drive or install location.
rem
rem 1. The App Paths registry entry Edge writes at install is the authoritative
rem    location, the Windows equivalent of "which". Check the native and the
rem    WOW6432Node views, machine-wide then per-user. Parse the value without
rem    find or findstr, by matching the REG_SZ token directly, so nothing
rem    depends on those tools being the Windows versions on the PATH.
rem 2. If the registry is somehow missing, fall back to the standard folders
rem    built from the real Program Files environment variables, which resolve
rem    correctly even when Windows is not on C:.
rem 3. As a last resort try the literal C: paths.
rem
rem Every path here stays quoted, and the launch happens at a goto label below
rem rather than inside a parenthesised block, so a path containing "(x86)" can
rem never break parsing.
set "EDGE_EXE="
for %%K in (
    "HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe"
    "HKLM\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe"
    "HKCU\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe"
) do if not defined EDGE_EXE for /f "tokens=2,*" %%a in ('reg query "%%~K" /ve 2^>nul') do if "%%a"=="REG_SZ" set "EDGE_EXE=%%b"

if not defined EDGE_EXE if exist "%ProgramFiles%\Microsoft\Edge\Application\msedge.exe" set "EDGE_EXE=%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"
if not defined EDGE_EXE if exist "%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe" set "EDGE_EXE=%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"
if not defined EDGE_EXE if exist "C:\Program Files\Microsoft\Edge\Application\msedge.exe" set "EDGE_EXE=C:\Program Files\Microsoft\Edge\Application\msedge.exe"
if not defined EDGE_EXE if exist "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" set "EDGE_EXE=C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

cd /d "%ROOT%"
rem Run through cmd /c rather than launching python directly, so that if the
rem server exits with a non-zero code (a malformed YAML edit, a missing file
rem after an incomplete copy) the window pauses instead of closing instantly.
rem app/main.py also writes the reason to startup-error.txt in this folder.
start "SawahPintar server" /min cmd /c ""%PYTHON_EXE%" -m app.main --port %PORT% --simulate || pause"

rem Wait for the server to actually accept connections before opening the
rem browser. The first run generates about 90 days of demonstration history,
rem which can take half a minute, so poll the port rather than guess with a
rem fixed delay that opens the browser onto a connection error. The poll uses
rem the bundled interpreter, which is guaranteed present, rather than any
rem external tool that a fresh laptop might lack.
echo Starting SawahPintar.
echo The first run takes a little longer while it prepares the demonstration
echo history. Please wait, the screen will open on its own.

set /a TRIES=0
:waitloop
"%PYTHON_EXE%" -c "import socket,sys; s=socket.socket(); s.settimeout(1); r=s.connect_ex(('127.0.0.1',%PORT%)); s.close(); sys.exit(0 if r==0 else 1)" >nul 2>&1
if not errorlevel 1 goto ready
set /a TRIES+=1
if %TRIES% geq 120 goto giveup
timeout /t 1 /nobreak >nul
goto waitloop

:ready
rem Prefer Edge in application mode for a clean full-screen window with no
rem browser furniture. If no Edge was found, open the default browser instead,
rem so the application still works on a laptop that does not have Edge. The
rem launch lines sit at labels, outside any parenthesised block, so a quoted
rem path containing "(x86)" is always safe.
if defined EDGE_EXE goto launchedge
start "" "http://127.0.0.1:%PORT%"
exit /b 0

:launchedge
start "" "%EDGE_EXE%" --app=http://127.0.0.1:%PORT%
exit /b 0

:nopython
echo Could not find the bundled Python runtime at:
echo   %PYTHON_EXE%
echo.
echo This folder is missing its "python" sub-folder. Copy the WHOLE
echo SawahPintar folder again from the distribution, not just part of it.
pause
exit /b 1

:giveup
echo.
echo The server did not become ready in time.
echo Open startup-error.txt in this folder to see what went wrong.
pause
exit /b 1
