@echo off
REM migrate.bat [CONTAINER_NAME] [DB_NAME] [DB_USER] [MIG_DIR]
REM Defaults: microjobs-db-1 joblink joblink ..\db\init

setlocal enableextensions enabledelayedexpansion

:: Arguments / Defaults
set CONTAINER=%1
if "%CONTAINER%"=="" set CONTAINER=08262f5a7112cc840cc5c4623e7579dbc3598d25eccd8f97b9595f9339bf4ac0

set DB=%2
if "%DB%"=="" set DB=joblink

set USER=%3
if "%USER%"=="" set USER=joblink

set DEFAULT_MIGDIR=%~dp0..\db\init
set MIGDIR=%4
if "%MIGDIR%"=="" set MIGDIR=%DEFAULT_MIGDIR%

:: Show config
echo.
echo === Migration Config ===
echo Container : %CONTAINER%
echo Database  : %DB%
echo User      : %USER%
echo Directory : %MIGDIR%
echo ========================
echo.

:: Validate directory
if not exist "%MIGDIR%" (
  echo ERROR: Migration directory not found: %MIGDIR%
  exit /b 2
)

:: Apply migrations
set COUNT=0
for %%F in ("%MIGDIR%\*.sql") do (
  echo Applying migration: %%~nxF
  docker exec -i %CONTAINER% psql -U %USER% -d %DB% < "%%F"
  if errorlevel 1 (
    echo ERROR: Migration failed on %%~nxF
    exit /b 1
  )
  set /a COUNT+=1
  echo   -> Success
  echo.
)

echo All migrations applied successfully. Total: %COUNT%
endlocal
