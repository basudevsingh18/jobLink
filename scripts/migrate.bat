@echo off
REM Usage: migrate.bat [CONTAINER_NAME] [DB_NAME] [DB_USER] [MIG_DIR]
REM Defaults: jl_postgres joblink joblink ..\db\init
setlocal enableextensions enabledelayedexpansion

set CONTAINER=%1
if "%CONTAINER%"=="" set CONTAINER=joblink-db-1

set DB=%2
if "%DB%"=="" set DB=joblink

set USER=%3
if "%USER%"=="" set USER=joblink

set DEFAULT_MIGDIR=%~dp0..\db\init
set MIGDIR=%4
if "%MIGDIR%"=="" set MIGDIR=%DEFAULT_MIGDIR%

if not exist "%MIGDIR%" (
  echo Migration directory not found: %MIGDIR%
  exit /b 2
)

for %%F in ("%MIGDIR%\*.sql") do (
  echo Applying %%~nxF
  docker exec -i %CONTAINER% psql -U %USER% -d %DB% < "%%F"
)

echo Migrations completed.
