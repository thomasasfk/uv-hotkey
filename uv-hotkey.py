#!/usr/bin/env python3
# /// script
# requires-python = ">=3.13"
# dependencies = [
#   "pyside6>=6.5.0",
#   "keyboard>=0.13.5",
#   "appdirs>=1.4.4",
#   "loguru>=0.7.0",
# ]
# ///

import sys
import os
import json
import subprocess
import appdirs
from pathlib import Path
from functools import partial

from PySide6.QtWidgets import (
    QApplication, QSystemTrayIcon, QMenu, QDialog, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit, QFileDialog, QMessageBox, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView, QFrame, QStyle, QStyleFactory,
)
from PySide6.QtGui import QIcon, QAction, QFont, QPalette, QColor
from PySide6.QtCore import Qt, QModelIndex

import keyboard
from loguru import logger

APP_NAME = "uv-hotkey"
DATA_DIR = Path(".data") if os.getenv('DEV') else Path(appdirs.user_data_dir(APP_NAME))
LOGS_DIR = DATA_DIR / ".logs"
CONFIG_FILE = DATA_DIR / "config.json"
SCRIPTS_DIR = DATA_DIR / "scripts"
ICON_PATH = Path(__file__).parent / "app_icon.png"


def setup_logging():
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_file = LOGS_DIR / f"{APP_NAME}.log"
    logger.remove()
    logger.add(sys.stderr, level="INFO")
    logger.add(log_file, level="DEBUG")
    logger.info(f"Logging to {log_file}")


class DarkTheme:
    @staticmethod
    def apply(app):
        app.setStyle(QStyleFactory.create("Fusion"))
        dark_palette = QPalette()
        dark_color = QColor(45, 45, 45)
        disabled_color = QColor(127, 127, 127)
        text_color = QColor(210, 210, 210)
        highlight_color = QColor(42, 130, 218)

        dark_palette.setColor(QPalette.Window, dark_color)
        dark_palette.setColor(QPalette.WindowText, text_color)
        dark_palette.setColor(QPalette.Base, QColor(25, 25, 25))
        dark_palette.setColor(QPalette.AlternateBase, dark_color)
        dark_palette.setColor(QPalette.ToolTipBase, highlight_color)
        dark_palette.setColor(QPalette.ToolTipText, text_color)
        dark_palette.setColor(QPalette.Text, text_color)
        dark_palette.setColor(QPalette.Disabled, QPalette.Text, disabled_color)
        dark_palette.setColor(QPalette.Button, dark_color)
        dark_palette.setColor(QPalette.ButtonText, text_color)
        dark_palette.setColor(QPalette.Disabled, QPalette.ButtonText, disabled_color)
        dark_palette.setColor(QPalette.BrightText, Qt.red)
        dark_palette.setColor(QPalette.Link, highlight_color)
        dark_palette.setColor(QPalette.Highlight, highlight_color)
        dark_palette.setColor(QPalette.HighlightedText, Qt.black)
        dark_palette.setColor(QPalette.Disabled, QPalette.HighlightedText, disabled_color)
        app.setPalette(dark_palette)


class StyledButton(QPushButton):
    def __init__(self, text, icon_name=None, parent=None):
        super().__init__(text, parent)
        self.setMinimumWidth(80)
        self.setMaximumWidth(120)
        if icon_name:
            self.setIcon(self.style().standardIcon(getattr(QStyle, icon_name)))


class HotkeyItem:
    def __init__(self, hotkey="", script_path="", name="", env_vars=None):
        self.hotkey = hotkey
        self.script_path = script_path
        self.name = name or (os.path.basename(script_path) if script_path else "")
        self.env_vars = env_vars if env_vars is not None else {}

    def to_dict(self):
        return {"hotkey": self.hotkey, "script_path": self.script_path, "name": self.name, "env_vars": self.env_vars}

    @classmethod
    def from_dict(cls, data):
        return cls(
            hotkey=data.get("hotkey", ""), script_path=data.get("script_path", ""),
            name=data.get("name", ""), env_vars=data.get("env_vars", {})
        )


class HotkeyManager:
    def __init__(self):
        self.hotkeys = []
        self.global_env_vars = {}
        logger.info(f"Using data directory: {DATA_DIR}")
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        SCRIPTS_DIR.mkdir(exist_ok=True)
        self.load_config()

    def load_config(self):
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, 'r') as f:
                    data = json.load(f)
                self.hotkeys = [HotkeyItem.from_dict(item) for item in data.get("hotkeys", [])]
                self.global_env_vars = data.get("global_env_vars", {})
                logger.info(f"Loaded {len(self.hotkeys)} hotkeys, {len(self.global_env_vars)} global env vars.")
            except (json.JSONDecodeError, IOError) as e:
                logger.error(f"Failed to load config {CONFIG_FILE}: {e}")
                self.hotkeys, self.global_env_vars = [], {}
        else:
            logger.info("No config file found. Starting fresh.")
            self.hotkeys, self.global_env_vars = [], {}

    def save_config(self):
        logger.debug("Saving configuration.")
        config = {"hotkeys": [item.to_dict() for item in self.hotkeys], "global_env_vars": self.global_env_vars}
        try:
            with open(CONFIG_FILE, 'w') as f:
                json.dump(config, f, indent=2)
        except IOError as e:
            logger.error(f"Failed to save config {CONFIG_FILE}: {e}")

    def register_all_hotkeys(self):
        logger.debug("Registering hotkeys...")
        keyboard.unhook_all()
        count = 0
        for item in self.hotkeys:
            if item.hotkey and item.script_path:
                try:
                    keyboard.add_hotkey(item.hotkey, partial(self.run_script, item))
                    count += 1
                except Exception as e:
                    logger.error(f"Failed to register hotkey '{item.hotkey}' for '{item.name}': {e}")
        logger.info(f"Registered {count} hotkeys.")

    def run_script(self, hotkey_item: HotkeyItem):
        logger.info(f"Running script: {hotkey_item.name} ({hotkey_item.hotkey})")
        if not os.path.exists(hotkey_item.script_path):
            logger.error(f"Script not found: {hotkey_item.script_path}")
            return
        try:
            env = os.environ.copy()
            env.update(self.global_env_vars)
            env.update(hotkey_item.env_vars)
            subprocess.Popen(
                ["uv", "run", "--script", hotkey_item.script_path],
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
                env=env
            )
        except Exception as e:
            logger.error(f"Error launching script {hotkey_item.name}: {e}")

    def add_hotkey(self, hotkey_item):
        logger.info(f"Adding hotkey: {hotkey_item.name}")
        self.hotkeys.append(hotkey_item)
        self.save_config()
        self.register_all_hotkeys()

    def update_hotkey(self, index, hotkey_item):
        if 0 <= index < len(self.hotkeys):
            logger.info(f"Updating hotkey: {hotkey_item.name}")
            self.hotkeys[index] = hotkey_item
            self.save_config()
            self.register_all_hotkeys()

    def remove_hotkey(self, index):
        if 0 <= index < len(self.hotkeys):
            removed_name = self.hotkeys[index].name
            logger.info(f"Removing hotkey: {removed_name}")
            del self.hotkeys[index]
            self.save_config()
            self.register_all_hotkeys()

    def set_global_env_vars(self, env_vars):
        logger.info(f"Setting {len(env_vars)} global environment variables.")
        self.global_env_vars = env_vars
        self.save_config()


class EnvVarDialog(QDialog):
    def __init__(self, env_vars=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Environment Variables")
        self.resize(400, 300)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.env_vars_initial = env_vars or {}
        self.setup_ui()
        self.populate_env_vars()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(15, 15, 15, 15)
        self.env_table = QTableWidget(0, 2)
        self.env_table.setHorizontalHeaderLabels(["Variable", "Value"])
        self.env_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.env_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        layout.addWidget(self.env_table)

        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)
        self.add_var_button = StyledButton("Add", "SP_FileIcon")
        self.add_var_button.clicked.connect(self.add_env_var)
        self.remove_var_button = StyledButton("Remove", "SP_TrashIcon")
        self.remove_var_button.clicked.connect(self.remove_env_var)
        button_layout.addWidget(self.add_var_button)
        button_layout.addWidget(self.remove_var_button)
        button_layout.addStretch()
        layout.addLayout(button_layout)

        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)
        layout.addWidget(separator)

        dialog_buttons = QHBoxLayout()
        self.save_button = StyledButton("Save", "SP_DialogSaveButton")
        self.save_button.clicked.connect(self.accept)
        self.cancel_button = StyledButton("Cancel", "SP_DialogCancelButton")
        self.cancel_button.clicked.connect(self.reject)
        dialog_buttons.addStretch()
        dialog_buttons.addWidget(self.save_button)
        dialog_buttons.addWidget(self.cancel_button)
        layout.addLayout(dialog_buttons)

    def populate_env_vars(self):
        self.env_table.setRowCount(0)
        for row, (key, value) in enumerate(self.env_vars_initial.items()):
            self.env_table.insertRow(row)
            self.env_table.setItem(row, 0, QTableWidgetItem(key))
            self.env_table.setItem(row, 1, QTableWidgetItem(value))

    def add_env_var(self):
        row = self.env_table.rowCount()
        self.env_table.insertRow(row)
        self.env_table.selectRow(row)
        self.env_table.setFocus()
        self.env_table.editItem(self.env_table.item(row, 0) or QTableWidgetItem(""))  # Ensure item exists

    def remove_env_var(self):
        selected_rows = sorted(set(index.row() for index in self.env_table.selectedIndexes()), reverse=True)
        for row in selected_rows: self.env_table.removeRow(row)

    def get_env_vars(self):
        env_vars = {}
        for row in range(self.env_table.rowCount()):
            key_item = self.env_table.item(row, 0)
            value_item = self.env_table.item(row, 1)
            key = key_item.text().strip() if key_item else ""
            if key: env_vars[key] = value_item.text() if value_item else ""
        return env_vars


class HotkeyDialog(QDialog):
    def __init__(self, hotkey_item=None, parent=None):
        super().__init__(parent)
        self.hotkey_item = hotkey_item or HotkeyItem()
        self.setWindowTitle("Hotkey Configuration")
        self.resize(500, 220)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.recording = False
        self.pressed_keys = set()
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(15, 15, 15, 15)

        def add_row(label_text, widget):
            row_layout = QHBoxLayout()
            label = QLabel(label_text)
            label.setMinimumWidth(60)
            row_layout.addWidget(label)
            row_layout.addWidget(widget)
            return row_layout

        self.name_edit = QLineEdit(self.hotkey_item.name)
        layout.addLayout(add_row("Name:", self.name_edit))

        self.hotkey_edit = QLineEdit(self.hotkey_item.hotkey)
        self.hotkey_edit.setPlaceholderText("Click to record hotkey")
        self.hotkey_edit.setReadOnly(True)
        self.hotkey_edit.mousePressEvent = self.start_recording
        layout.addLayout(add_row("Hotkey:", self.hotkey_edit))

        script_layout = QHBoxLayout()
        script_label = QLabel("Script:")
        script_label.setMinimumWidth(60)
        self.script_edit = QLineEdit(self.hotkey_item.script_path)
        self.browse_button = StyledButton("Browse", "SP_DirOpenIcon")
        self.browse_button.clicked.connect(self.browse_script)
        self.browse_button.setMaximumWidth(80)
        script_layout.addWidget(script_label)
        script_layout.addWidget(self.script_edit)
        script_layout.addWidget(self.browse_button)
        layout.addLayout(script_layout)

        env_layout = QHBoxLayout()
        env_label = QLabel("Env Vars:")
        env_label.setMinimumWidth(60)
        self.env_count_label = QLabel(f"{len(self.hotkey_item.env_vars)} set")
        self.env_button = StyledButton("Edit", "SP_FileDialogDetailedView")
        self.env_button.clicked.connect(self.edit_env_vars)
        self.env_button.setMaximumWidth(80)
        env_layout.addWidget(env_label)
        env_layout.addWidget(self.env_count_label)
        env_layout.addStretch()
        env_layout.addWidget(self.env_button)
        layout.addLayout(env_layout)

        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)
        layout.addWidget(separator)

        button_layout = QHBoxLayout()
        self.save_button = StyledButton("Save", "SP_DialogSaveButton")
        self.save_button.clicked.connect(self.accept)
        self.cancel_button = StyledButton("Cancel", "SP_DialogCancelButton")
        self.cancel_button.clicked.connect(self.reject)
        button_layout.addStretch()
        button_layout.addWidget(self.save_button)
        button_layout.addWidget(self.cancel_button)
        layout.addLayout(button_layout)

    def start_recording(self, _):
        if not self.recording:
            self.recording = True
            self.original_hotkey = self.hotkey_edit.text()
            self.hotkey_edit.setText("Press hotkey combination...")
            self.pressed_keys.clear()
            keyboard.hook(self.on_key_event)

    def on_key_event(self, event):
        if self.recording and event.event_type == keyboard.KEY_DOWN:
            try:
                if event.scan_code == 1:  # Escape key scan code
                    logger.debug("Escape pressed, canceling hotkey recording")
                    self.hotkey_edit.setText(self.original_hotkey)
                    self.recording = False
                    keyboard.unhook(self.on_key_event)
                    return

                hotkey = keyboard.read_hotkey()
                logger.debug(f"Recorded hotkey: {hotkey}")
                self.hotkey_edit.setText(hotkey)
                self.recording = False
                keyboard.unhook(self.on_key_event)
            except Exception as e:
                logger.error(f"Error recording hotkey: {e}")
                self.hotkey_edit.setText(self.original_hotkey)
                self.recording = False
                keyboard.unhook(self.on_key_event)

    def browse_script(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Select Script", str(SCRIPTS_DIR), "Python Files (*.py)")
        if file_path:
            self.script_edit.setText(file_path)
            if not self.name_edit.text(): self.name_edit.setText(os.path.basename(file_path))

    def edit_env_vars(self):
        dialog = EnvVarDialog(self.hotkey_item.env_vars, self)
        if dialog.exec():
            self.hotkey_item.env_vars = dialog.get_env_vars()
            self.env_count_label.setText(f"{len(self.hotkey_item.env_vars)} set")

    def get_hotkey_item(self):
        name = self.name_edit.text() or (os.path.basename(self.script_edit.text()) if self.script_edit.text() else "")
        return HotkeyItem(self.hotkey_edit.text(), self.script_edit.text(), name, self.hotkey_item.env_vars)


class MainWindow(QDialog):
    def __init__(self, manager):
        super().__init__()
        self.manager = manager
        self.setWindowTitle(APP_NAME)
        self.resize(600, 400)
        if ICON_PATH.exists():
            self.setWindowIcon(QIcon(str(ICON_PATH)))
        else:
            logger.warning(f"Icon file not found: {ICON_PATH}")
        self.setup_ui()
        self.populate_hotkey_table()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(15, 15, 15, 15)

        header_layout = QHBoxLayout()
        title_label = QLabel(APP_NAME)
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title_label.setFont(title_font)
        header_layout.addWidget(title_label)
        header_layout.addStretch()
        self.global_env_button = StyledButton("Global Env", "SP_FileDialogDetailedView")
        self.global_env_button.clicked.connect(self.edit_global_env_vars)
        self.global_env_button.setMaximumWidth(100)
        header_layout.addWidget(self.global_env_button)
        layout.addLayout(header_layout)

        self.hotkey_table = QTableWidget(0, 4)
        self.hotkey_table.setHorizontalHeaderLabels(["Hotkey", "Name", "Env Vars", "Script Path"])
        self.hotkey_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.hotkey_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.hotkey_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.hotkey_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.hotkey_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.hotkey_table.verticalHeader().setVisible(False)
        self.hotkey_table.setAlternatingRowColors(True)
        self.hotkey_table.doubleClicked.connect(self.edit_hotkey)
        layout.addWidget(self.hotkey_table)

        button_layout = QHBoxLayout()
        left_buttons = QHBoxLayout()
        self.add_button = StyledButton("Add", "SP_FileIcon")
        self.add_button.clicked.connect(self.add_hotkey)
        self.edit_button = StyledButton("Edit", "SP_FileDialogDetailedView")
        self.edit_button.clicked.connect(self.edit_hotkey)
        self.remove_button = StyledButton("Remove", "SP_TrashIcon")
        self.remove_button.clicked.connect(self.remove_hotkey)
        left_buttons.addWidget(self.add_button)
        left_buttons.addWidget(self.edit_button)
        left_buttons.addWidget(self.remove_button)
        left_buttons.addStretch()

        right_buttons = QHBoxLayout()
        self.logs_button = StyledButton("Logs", "SP_FileDialogInfoView")
        self.logs_button.clicked.connect(self.open_logs_directory)
        self.logs_button.setMaximumWidth(80)
        right_buttons.addWidget(self.logs_button)

        button_layout.addLayout(left_buttons)
        button_layout.addLayout(right_buttons)
        layout.addLayout(button_layout)

    def edit_global_env_vars(self):
        dialog = EnvVarDialog(self.manager.global_env_vars, self)
        dialog.setWindowTitle("Global Environment Variables")
        if dialog.exec():
            self.manager.set_global_env_vars(dialog.get_env_vars())

    def open_logs_directory(self):
        logger.info(f"Opening logs directory: {LOGS_DIR}")
        if LOGS_DIR.exists():
            try:
                if sys.platform == 'win32':
                    os.startfile(LOGS_DIR)
                elif sys.platform == 'darwin':
                    subprocess.call(['open', LOGS_DIR])
                else:
                    subprocess.call(['xdg-open', LOGS_DIR])
            except Exception as e:
                logger.error(f"Could not open logs directory {LOGS_DIR}: {e}")
                QMessageBox.warning(self, "Error", f"Could not open logs directory:\n{LOGS_DIR}")
        else:
            QMessageBox.warning(self, "Error", "Logs directory not found.")

    def populate_hotkey_table(self):
        self.hotkey_table.setRowCount(0)
        for i, item in enumerate(self.manager.hotkeys):
            self.hotkey_table.insertRow(i)
            self.hotkey_table.setItem(i, 0, QTableWidgetItem(item.hotkey))
            self.hotkey_table.setItem(i, 1, QTableWidgetItem(item.name))
            env_text = f"{len(item.env_vars)} vars" if item.env_vars else ""
            if item.env_vars:
                env_keys = list(item.env_vars.keys())
                if len(env_keys) <= 3:
                    env_text = ", ".join(env_keys)
                else:
                    env_text = f"({len(env_keys)}) " + ", ".join(env_keys[:2]) + "..."
            self.hotkey_table.setItem(i, 2, QTableWidgetItem(env_text))
            self.hotkey_table.setItem(i, 3, QTableWidgetItem(item.script_path))
        self.hotkey_table.resizeColumnsToContents()

    def add_hotkey(self):
        dialog = HotkeyDialog(parent=self)
        if dialog.exec():
            self.manager.add_hotkey(dialog.get_hotkey_item())
            self.populate_hotkey_table()

    def edit_hotkey(self, index=None):
        row = index.row() if isinstance(index, QModelIndex) and index.isValid() else self.hotkey_table.currentRow()
        if 0 <= row < len(self.manager.hotkeys):
            dialog = HotkeyDialog(self.manager.hotkeys[row], parent=self)
            if dialog.exec():
                self.manager.update_hotkey(row, dialog.get_hotkey_item())
                self.populate_hotkey_table()

    def remove_hotkey(self):
        row = self.hotkey_table.currentRow()
        if row >= 0:
            item_name = self.manager.hotkeys[row].name
            if QMessageBox.question(
                    self, "Confirm Removal", f"Remove '{item_name}'?", QMessageBox.Yes | QMessageBox.No
            ) == QMessageBox.Yes:
                self.manager.remove_hotkey(row)
                self.populate_hotkey_table()

    def closeEvent(self, event):
        self.hide()
        event.ignore()


if __name__ == "__main__":
    setup_logging()
    logger.info(f"Starting {APP_NAME}")
    app = QApplication(sys.argv)
    DarkTheme.apply(app)
    app.setQuitOnLastWindowClosed(False)

    if not QSystemTrayIcon.isSystemTrayAvailable():
        QMessageBox.critical(None, "Error", "System tray not available.")
        logger.critical("System tray not available, exiting.")
        sys.exit(1)

    if not ICON_PATH.exists():
        logger.error(f"Required icon file not found at {ICON_PATH}, tray icon may be missing.")

    hotkey_manager = HotkeyManager()
    main_window = MainWindow(hotkey_manager)

    tray_icon = QSystemTrayIcon(QIcon(str(ICON_PATH)) if ICON_PATH.exists() else QIcon())
    tray_menu = QMenu()

    open_action = QAction("Open Manager")
    open_action.triggered.connect(main_window.show)
    tray_menu.addAction(open_action)
    logs_action = QAction("View Logs")
    logs_action.triggered.connect(main_window.open_logs_directory)
    tray_menu.addAction(logs_action)
    quit_action = QAction("Quit")
    quit_action.triggered.connect(lambda: logger.info("Quitting application.") or app.quit())
    tray_menu.addAction(quit_action)

    tray_icon.setContextMenu(tray_menu)
    tray_icon.activated.connect(
        lambda reason: main_window.show() if reason == QSystemTrayIcon.ActivationReason.Trigger else None
    )
    tray_icon.show()
    logger.info("System tray icon active.")

    hotkey_manager.register_all_hotkeys()
    logger.info(f"{APP_NAME} is running.")
    sys.exit(app.exec())
