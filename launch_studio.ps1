# C:\OmniCreator_Studio\launch_studio.ps1
$StreamlitExe = "C:\YouTube_Studio_Engine\.venv\Scripts\streamlit.exe"
$AppPath = Join-Path $PSScriptRoot "app.py"
Write-Host "Starting OmniCreator Studio at http://localhost:8501 ..." -ForegroundColor Green
& $StreamlitExe run $AppPath --server.port 8501
