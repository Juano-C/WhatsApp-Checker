from pathlib import Path

from PySide6.QtCore import QDate, QThread, Signal
from PySide6.QtWidgets import QAbstractItemView
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMainWindow,
    QMessageBox, QProgressBar, QPushButton, QTableWidget, QTableWidgetItem,
    QTabWidget, QVBoxLayout, QWidget, QDateEdit, QComboBox, QInputDialog, QCheckBox,
)

from .database import Database
from .parser import iter_messages
from .updater import UpdateWorker, install_update
from .version import APP_VERSION


class ImportWorker(QThread):
    finished_import = Signal(int, int)
    failed = Signal(str)

    def __init__(self, database, path, name):
        super().__init__()
        self.database, self.path, self.name = database, path, name

    def run(self):
        try:
            result = self.database.import_messages(self.name, self.path, iter_messages(self.path))
            self.finished_import.emit(*result)
        except Exception as error:
            self.failed.emit(str(error))


class MainWindow(QMainWindow):
    def __init__(self, database: Database):
        super().__init__()
        self.database = database
        self.current_rows = []
        self.setWindowTitle("WhatsApp Chat Analyzer")
        self.resize(1050, 650)
        self._build_ui()
        self.refresh_chats()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        top = QHBoxLayout()
        self.import_button = QPushButton("Importar chat .txt")
        self.import_button.clicked.connect(self.import_chat)
        self.export_button = QPushButton("Exportar resultados CSV")
        self.export_button.clicked.connect(self.export_results)
        self.snapshot_button = QPushButton("Guardar corte")
        self.snapshot_button.clicked.connect(self.save_snapshot)
        self.system_messages = QCheckBox("Mensajes de sistema")
        self.system_messages.setToolTip("Incluir mensajes automáticos de WhatsApp en los resultados")
        self.system_messages.stateChanged.connect(self.system_filter_changed)
        self.update_button = QPushButton("Actualizar")
        self.update_button.clicked.connect(self.check_for_updates)
        top.addWidget(self.import_button)
        top.addWidget(self.export_button)
        top.addWidget(self.snapshot_button)
        top.addWidget(self.system_messages)
        top.addWidget(self.update_button)
        self.status = QLabel("Listo")
        top.addWidget(self.status, 1)
        layout.addLayout(top)

        filters = QFormLayout()
        self.chat = QComboBox()
        self.chat.currentTextChanged.connect(self.refresh)
        self.text = QLineEdit()
        self.text.setPlaceholderText("Buscar dentro del mensaje")
        self.contact = QComboBox()
        self.contact.setEditable(False)
        self.contact.currentTextChanged.connect(self.refresh)
        self.start = QDateEdit(QDate(2000, 1, 1)); self.start.setCalendarPopup(True)
        self.end = QDateEdit(QDate.currentDate()); self.end.setCalendarPopup(True)
        self.start.setFixedWidth(135); self.end.setFixedWidth(135)
        self.start.lineEdit().setReadOnly(True); self.end.lineEdit().setReadOnly(True)
        self.text.returnPressed.connect(self.refresh)
        filters.addRow("Chat:", self.chat)
        filters.addRow("Texto:", self.text)
        filters.addRow("Contacto:", self.contact)
        date_row = QHBoxLayout(); date_row.setSpacing(6)
        date_row.addWidget(self.start); date_row.addWidget(QLabel("hasta")); date_row.addWidget(self.end)
        date_row.addStretch()
        filters.addRow("Fecha:", date_row)
        search = QPushButton("Buscar")
        search.clicked.connect(self.refresh)
        filters.addRow("", search)
        layout.addLayout(filters)

        self.tabs = QTabWidget()
        self.messages = QTableWidget(0, 4)
        self.messages.setHorizontalHeaderLabels(["Fecha", "Hora", "Contacto", "Mensaje"])
        self.messages.horizontalHeader().setStretchLastSection(True)
        self.messages.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabs.addTab(self.messages, "Mensajes")
        self.stats_table = QTableWidget(0, 2)
        self.stats_table.setHorizontalHeaderLabels(["Contacto", "Mensajes"])
        self.stats_table.horizontalHeader().setStretchLastSection(True)
        self.stats_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabs.addTab(self.stats_table, "Estadísticas")
        contacts_page = QWidget()
        contacts_layout = QVBoxLayout(contacts_page)
        self.contacts_table = QTableWidget(0, 3)
        self.contacts_table.setHorizontalHeaderLabels(["Contacto", "Original", "Mensajes en el período"])
        self.contacts_table.setColumnHidden(1, True)
        self.contacts_table.horizontalHeader().setStretchLastSection(True)
        self.contacts_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        contacts_layout.addWidget(self.contacts_table)
        contact_buttons = QHBoxLayout()
        add_contact = QPushButton("Agregar contacto")
        add_contact.clicked.connect(self.add_contact)
        rename_contact = QPushButton("Renombrar seleccionado")
        rename_contact.clicked.connect(self.rename_contact)
        delete_contact = QPushButton("Eliminar seleccionado")
        delete_contact.clicked.connect(self.delete_contact)
        contact_buttons.addWidget(add_contact)
        contact_buttons.addWidget(rename_contact)
        contact_buttons.addWidget(delete_contact)
        contact_buttons.addStretch()
        contacts_layout.addLayout(contact_buttons)
        self.tabs.addTab(contacts_page, "Contactos")
        snapshots_page = QWidget()
        snapshots_layout = QVBoxLayout(snapshots_page)
        self.snapshots_table = QTableWidget(0, 5)
        self.snapshots_table.setHorizontalHeaderLabels(["Nombre", "Chat", "Período", "Filtro", "Creado"])
        self.snapshots_table.horizontalHeader().setStretchLastSection(True)
        self.snapshots_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.snapshots_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.snapshots_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        snapshots_layout.addWidget(self.snapshots_table)
        compare = QPushButton("Comparar dos cortes seleccionados")
        compare.clicked.connect(self.compare_snapshots)
        snapshots_layout.addWidget(compare)
        self.tabs.addTab(snapshots_page, "Cortes guardados")
        self.tabs.currentChanged.connect(lambda _: self.refresh())
        layout.addWidget(self.tabs)

    def refresh_chats(self):
        current = self.chat.currentText()
        self.chat.blockSignals(True); self.chat.clear(); self.chat.addItems(self.database.chat_names())
        if current in self.database.chat_names(): self.chat.setCurrentText(current)
        self.chat.blockSignals(False)
        self.refresh_contacts()
        self.refresh()

    def system_filter_changed(self):
        self.refresh_contacts()
        self.refresh()

    def refresh_contacts(self):
        if not self.chat.currentText():
            return
        current = self.contact.currentText()
        self.contact.blockSignals(True)
        self.contact.clear()
        self.contact.addItem("")
        self.contact.addItems(self.database.contacts(
            self.chat.currentText(), self.system_messages.isChecked()))
        self.contact.setCurrentText(current)
        self.contact.blockSignals(False)

    def refresh(self):
        if not self.chat.currentText():
            return
        if self.tabs.currentIndex() == 1:
            rows = self.database.stats(
                self.chat.currentText(), self.text.text(), self.contact.currentText(),
                self.start.date().toString("yyyy-MM-dd"), self.end.date().toString("yyyy-MM-dd"),
                self.system_messages.isChecked())
            self.stats_table.setRowCount(len(rows))
            for row_index, row in enumerate(rows):
                self.stats_table.setItem(row_index, 0, QTableWidgetItem(row[0]))
                self.stats_table.setItem(row_index, 1, QTableWidgetItem(str(row[1])))
            return
        if self.tabs.currentIndex() == 2:
            self.refresh_contact_counts()
            return
        if self.tabs.currentIndex() == 3:
            self.refresh_snapshots()
            return
        self.current_rows = self.database.search(
            self.chat.currentText(), self.text.text(), self.contact.currentText(),
            self.start.date().toString("yyyy-MM-dd"), self.end.date().toString("yyyy-MM-dd"),
            self.system_messages.isChecked())
        self.messages.setRowCount(len(self.current_rows))
        for row_index, row in enumerate(self.current_rows):
            for column, value in enumerate(row):
                self.messages.setItem(row_index, column, QTableWidgetItem(str(value)))
        self.status.setText(f"{len(self.current_rows):,} mensajes encontrados")

    def import_chat(self):
        path, _ = QFileDialog.getOpenFileName(self, "Seleccionar chat exportado", "", "Texto (*.txt);;Todos (*.*)")
        if not path:
            return
        chat_name, accepted = QInputDialog.getText(
            self, "Nombre del chat", "Nombre para identificar este chat:",
            text=Path(path).stem,
        )
        if not accepted or not chat_name.strip():
            chat_name = Path(path).stem
        self.import_button.setEnabled(False)
        self.status.setText("Importando en segundo plano...")
        self.worker = ImportWorker(self.database, path, chat_name)
        self.worker.finished_import.connect(self.import_finished)
        self.worker.failed.connect(self.import_failed)
        self.worker.start()

    def import_finished(self, total, inserted):
        self.import_button.setEnabled(True)
        self.status.setText(f"Importados {total:,}; nuevos {inserted:,} mensajes")
        self.refresh_chats()
        self.chat.setCurrentText(self.worker.name)
        self.refresh()

    def import_failed(self, message):
        self.import_button.setEnabled(True)
        QMessageBox.critical(self, "Error de importación", message)
        self.status.setText("Error de importación")

    def check_for_updates(self):
        self.update_button.setEnabled(False)
        self.status.setText(f"Buscando actualizaciones... (versión {APP_VERSION})")
        self.update_worker = UpdateWorker()
        self.update_worker.update_available.connect(self.update_found)
        self.update_worker.no_update.connect(self.no_update_found)
        self.update_worker.failed.connect(self.update_failed)
        self.update_worker.start()

    def update_found(self, version, download_path):
        self.update_button.setEnabled(True)
        answer = QMessageBox.question(
            self, "Actualización disponible",
            f"Hay una nueva versión ({version}). ¿Descargar e instalar ahora?",
        )
        if answer == QMessageBox.StandardButton.Yes:
            if install_update(download_path):
                QApplication.instance().quit()
            else:
                QMessageBox.information(
                    self, "Ejecutable requerido",
                    "El actualizador automático funciona desde el archivo .exe publicado."
                )

    def no_update_found(self, version):
        self.update_button.setEnabled(True)
        self.status.setText(f"Ya tenés la última versión ({version})")

    def update_failed(self, message):
        self.update_button.setEnabled(True)
        QMessageBox.warning(self, "No se pudo actualizar", message)
        self.status.setText("No se pudo comprobar la actualización")

    def export_results(self):
        if not self.current_rows:
            QMessageBox.information(self, "Sin resultados", "No hay mensajes para exportar.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Guardar CSV", "mensajes.csv", "CSV (*.csv)")
        if path:
            self.database.export_csv(self.current_rows, path)
            self.status.setText(f"CSV guardado: {path}")

    def save_snapshot(self):
        if not self.chat.currentText():
            QMessageBox.information(self, "Sin chat", "Primero importá un chat.")
            return
        name, accepted = QInputDialog.getText(self, "Guardar corte", "Nombre del corte:")
        if not accepted or not name.strip():
            return
        start = self.start.date().toString("yyyy-MM-dd")
        end = self.end.date().toString("yyyy-MM-dd")
        self.database.save_snapshot(
            name.strip(), self.chat.currentText(), self.text.text(), self.contact.currentText(), start, end,
            self.system_messages.isChecked()
        )
        self.status.setText(f"Corte guardado: {name.strip()}")
        self.refresh_snapshots()

    def refresh_snapshots(self):
        rows = self.database.snapshots()
        self.snapshots_table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            filter_text = row[5] or "Todos"
            if row[6]:
                filter_text += " + sistema"
            values = [row[1], row[2], f"{row[3]} a {row[4]}", filter_text, row[8]]
            for column, value in enumerate(values):
                self.snapshots_table.setItem(row_index, column, QTableWidgetItem(str(value)))

    def refresh_contact_counts(self):
        rows = self.database.contact_counts(
            self.chat.currentText(), self.text.text(),
            self.start.date().toString("yyyy-MM-dd"), self.end.date().toString("yyyy-MM-dd"),
            self.system_messages.isChecked())
        self.contacts_table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            self.contacts_table.setItem(row_index, 0, QTableWidgetItem(row[1]))
            self.contacts_table.setItem(row_index, 1, QTableWidgetItem(row[0]))
            self.contacts_table.setItem(row_index, 2, QTableWidgetItem(str(row[2])))

    def selected_contact_original(self):
        selected = self.contacts_table.selectionModel().selectedRows()
        if not selected:
            return None
        return self.contacts_table.item(selected[0].row(), 1).text()

    def rename_contact(self):
        original = self.selected_contact_original()
        if not original:
            QMessageBox.information(self, "Seleccionar contacto", "Seleccioná un contacto primero.")
            return
        current = self.contacts_table.item(self.contacts_table.currentRow(), 0).text()
        alias, accepted = QInputDialog.getText(self, "Renombrar contacto", "Nombre visible:", text=current)
        if accepted and alias.strip():
            self.database.rename_contact(original, alias)
            self.refresh_contacts()
            self.refresh_contact_counts()
            self.refresh()

    def delete_contact(self):
        original = self.selected_contact_original()
        if not original:
            QMessageBox.information(self, "Seleccionar contacto", "Seleccioná un contacto primero.")
            return
        answer = QMessageBox.question(
            self, "Eliminar contacto", "Se quitará de la lista, pero no se borrarán sus mensajes. ¿Continuar?"
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.database.delete_contact(self.chat.currentText(), original)
            self.refresh_contacts()
            self.refresh_contact_counts()
            self.refresh()

    def add_contact(self):
        if not self.chat.currentText():
            QMessageBox.information(self, "Sin chat", "Primero importá un chat.")
            return
        contact, accepted = QInputDialog.getText(
            self, "Agregar contacto", "Nombre o número del contacto:"
        )
        if not accepted or not contact.strip():
            return
        if contact.strip() == "Sistema" and not self.system_messages.isChecked():
            self.system_messages.setChecked(True)
        self.database.add_contact(self.chat.currentText(), contact)
        self.refresh_contact_counts()

    def compare_snapshots(self):
        selected = self.snapshots_table.selectionModel().selectedRows()
        if len(selected) != 2:
            QMessageBox.information(self, "Seleccionar cortes", "Seleccioná exactamente dos cortes para comparar.")
            return
        snapshot_rows = self.database.snapshots()
        first = snapshot_rows[selected[0].row()]
        second = snapshot_rows[selected[1].row()]
        comparison = self.database.compare_snapshots(first[0], second[0])
        lines = [f"Comparación: {first[1]} → {second[1]}", ""]
        for row in comparison:
            delta = row[2] - row[1]
            sign = "+" if delta > 0 else ""
            lines.append(f"{row[0]}: {row[1]} → {row[2]} ({sign}{delta})")
        QMessageBox.information(self, "Comparación de cortes", "\n".join(lines))
