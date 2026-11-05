import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from .version import APP_VERSION, GITHUB_REPOSITORY


def version_tuple(value: str):
    numbers = re.findall(r"\d+", value)
    return tuple(int(number) for number in numbers[:3]) or (0, 0, 0)


class UpdateWorker(QThread):
    update_available = Signal(str, str)  # versión, archivo descargado
    no_update = Signal(str)
    failed = Signal(str)

    def run(self):
        try:
            request = urllib.request.Request(
                f"https://api.github.com/repos/{GITHUB_REPOSITORY}/releases/latest",
                headers={"User-Agent": "WhatsAppChatAnalyzer"},
            )
            with urllib.request.urlopen(request, timeout=20) as response:
                release = json.load(response)
            remote_version = release.get("tag_name", "").lstrip("vV")
            if version_tuple(remote_version) <= version_tuple(APP_VERSION):
                self.no_update.emit(APP_VERSION)
                return

            assets = release.get("assets", [])
            asset = next(
                (item for item in assets if item["name"].lower().endswith(".exe")), None
            )
            if asset is None:
                asset = next(
                    (item for item in assets if item["name"].lower().endswith(".zip")), None
                )
            if asset is None:
                raise RuntimeError("El Release no contiene un .exe ni un .zip descargable.")

            download_path = Path(tempfile.gettempdir()) / f"WhatsAppChatAnalyzer-{remote_version}.{asset['name'].split('.')[-1]}"
            download_request = urllib.request.Request(
                asset["browser_download_url"], headers={"User-Agent": "WhatsAppChatAnalyzer"}
            )
            with urllib.request.urlopen(download_request, timeout=120) as response:
                download_path.write_bytes(response.read())
            if download_path.suffix.lower() == ".zip":
                extracted = Path(tempfile.gettempdir()) / f"WhatsAppChatAnalyzer-{remote_version}.exe"
                with zipfile.ZipFile(download_path) as archive:
                    exe_name = next(name for name in archive.namelist() if name.lower().endswith(".exe"))
                    extracted.write_bytes(archive.read(exe_name))
                download_path.unlink(missing_ok=True)
                download_path = extracted
            self.update_available.emit(remote_version, str(download_path))
        except Exception as error:
            self.failed.emit(str(error))


def install_update(download_path: str) -> bool:
    if not getattr(sys, "frozen", False):
        return False
    target = Path(sys.executable).resolve()
    script = Path(tempfile.gettempdir()) / "whatsapp_checker_update.bat"
    script.write_text(
        "@echo off\n"
        "timeout /t 2 /nobreak >nul\n"
        f'copy /Y "{download_path}" "{target}" >nul\n'
        f'start "" "{target}"\n'
        'del "%~f0"\n',
        encoding="utf-8",
    )
    subprocess.Popen(["cmd", "/c", str(script)], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return True
