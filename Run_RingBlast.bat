@echo off
setlocal EnableExtensions DisableDelayedExpansion
title RingBlast
rem Work from the launcher folder, even from a shortcut or another drive.
pushd "%~dp0"
if errorlevel 1 goto folder_error

if not exist "app.py" goto clone_error
if not exist "requirements.txt" goto clone_error
if not exist "scripts\launch_ringblast.py" goto clone_error
if exist ".venv\Scripts\python.exe" goto launch
if exist ".venv" goto environment_error

py -3.12 --version >nul 2>&1
if errorlevel 1 goto python_error
echo Creating the private Python 3.12 environment...
py -3.12 -m venv ".venv"
if errorlevel 1 goto environment_error
if not exist ".venv\Scripts\python.exe" goto environment_error

:launch
".venv\Scripts\python.exe" -I "scripts\launch_ringblast.py"
if errorlevel 1 goto failed
popd
exit /b 0

:python_error
echo ERROR: Python 3.12 and the Windows Python launcher are required.
echo Install Python 3.12 64-bit from https://www.python.org/downloads/windows/
echo Select the Python launcher during installation. A per-user install is enough.
echo Then double-click this file again. Check installed versions with: py -0p
goto failed

:environment_error
echo ERROR: Could not create or run the private .venv environment.
echo Check that this folder is writable and Python 3.12 is installed.
echo If .venv already exists or setup was interrupted, rename it and try again.
goto failed

:clone_error
echo ERROR: Missing app.py, requirements.txt or scripts\launch_ringblast.py.
echo Keep this launcher in the complete RingBlast folder, not by itself.
goto failed

:failed
popd
goto wait_for_user

:folder_error
echo ERROR: Cannot open the RingBlast folder. Move the clone to a writable local folder.

:wait_for_user
echo.
echo RingBlast could not start. Read the error above before closing this window.
pause
exit /b 1
