@echo off
setlocal
cd /d "%~dp0"
if exist "D:\java\bin\java.exe" (
    "D:\java\bin\java.exe" -jar "runtime\logisim.exe" "snake.circ"
) else (
    java -jar "runtime\logisim.exe" "snake.circ"
)
if errorlevel 1 pause
endlocal
