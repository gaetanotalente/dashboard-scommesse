@echo off
chcp 65001 >nul
title Dashboard Pronostici
cd /d "%~dp0"

python --version >nul 2>&1
if errorlevel 1 (
  echo Python non trovato. Installalo da python.org e spunta "Add Python to PATH".
  pause
  exit /b 1
)

python -c "import streamlit, fpdf, plotly, scipy, pandas" >nul 2>&1
if errorlevel 1 (
  echo Installo i componenti necessari. Serve solo la prima volta...
  python -m pip install -r requirements.txt
  if errorlevel 1 (
    echo Installazione non riuscita. Controlla la connessione e riprova.
    pause
    exit /b 1
  )
)

echo Avvio in corso... il browser si apre da solo.
echo Per chiudere il programma chiudi questa finestra.
if not exist ".streamlit\config.toml" (
  mkdir ".streamlit" >nul 2>&1
  (
    echo [theme]
    echo base = "light"
    echo primaryColor = "#4A6FA5"
    echo backgroundColor = "#F6F8FB"
    echo secondaryBackgroundColor = "#FFFFFF"
    echo textColor = "#1F2937"
    echo font = "sans serif"
  ) > ".streamlit\config.toml"
)
python -m streamlit run app.py
pause
