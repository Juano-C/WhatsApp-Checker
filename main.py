import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from whatsapp_analyzer.database import Database
from whatsapp_analyzer.window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("WhatsApp Chat Analyzer")
    # En un ejecutable de PyInstaller, __file__ apunta a una carpeta temporal.
    # La base debe quedar junto al .exe para conservar los datos entre usos.
    app_dir = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent
    database = Database(app_dir / "data" / "chats.db")
    window = MainWindow(database)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
