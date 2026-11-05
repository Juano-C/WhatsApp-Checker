$ErrorActionPreference = "Stop"

Write-Host "Instalando dependencias de compilacion..."
python -m pip install -r requirements.txt pyinstaller

Write-Host "Generando ejecutable..."
python -m PyInstaller --noconfirm --clean --onefile --windowed `
    --name WhatsAppChatAnalyzer main.py

Write-Host "Creando archivo para distribuir..."
if (Test-Path "WhatsAppChatAnalyzer-Windows.zip") {
    Remove-Item "WhatsAppChatAnalyzer-Windows.zip" -Force
}
Compress-Archive -Path "dist\WhatsAppChatAnalyzer.exe" -DestinationPath "WhatsAppChatAnalyzer-Windows.zip"

Write-Host "Listo: WhatsAppChatAnalyzer-Windows.zip"
