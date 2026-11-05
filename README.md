# WhatsApp Chat Analyzer

Aplicación de escritorio para importar y analizar chats exportados desde WhatsApp.

## Requisitos

- Python 3.11+
- PySide6

## Ejecutar

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

En WhatsApp elegir **Exportar chat → Sin archivos** y luego importar el `.txt` desde la aplicación.

## Funcionalidades del prototipo

- Importación línea por línea, apta para archivos grandes.
- Detección de formatos habituales de Android/iPhone y fechas con año de dos o cuatro dígitos.
- Base SQLite local con índices.
- Filtros por texto, contacto y rango de fechas.
- Estadísticas por contacto.
- Exportación de los resultados filtrados a CSV.

Los datos se guardan localmente en `data/chats.db`.

## Crear un ejecutable para Windows

Desde PowerShell, ejecutar:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\build.ps1
```

El resultado será `WhatsAppChatAnalyzer-Windows.zip`. Compartí ese ZIP o subilo como archivo adjunto de un GitHub Release. El usuario solo necesita extraerlo y abrir `WhatsAppChatAnalyzer.exe`; la base de datos se creará en una carpeta `data` junto al ejecutable.

La aplicación incluye el botón **Actualizar**. Antes de compilar una nueva versión, aumentá `APP_VERSION` en `whatsapp_analyzer/version.py`, por ejemplo de `0.1.0` a `0.2.0`. Luego ejecutá `build.ps1` y subí el ZIP a un nuevo GitHub Release con una etiqueta como `v0.2.0`.
