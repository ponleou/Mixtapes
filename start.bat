@echo off
REM Activate virtual environment and run Mixtapes

if exist .venv\Scripts\activate.bat (
    call .venv\Scripts\activate.bat
)

python src\main.py %*
