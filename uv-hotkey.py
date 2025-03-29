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
import datetime
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


class AppStyles:
    DIALOG_SPACING = 10
    DIALOG_MARGINS = (15, 15, 15, 15)
    ENV_DIALOG_SIZE = (400, 300)
    HOTKEY_DIALOG_SIZE = (500, 220)
    MAIN_WINDOW_SIZE = (600, 400)

    BUTTON_MIN_WIDTH = 80
    BUTTON_MAX_WIDTH = 120

    LABEL_MIN_WIDTH = 60

    TITLE_FONT_SIZE = 14

    @staticmethod
    def apply_dark_theme(app):
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

    @staticmethod
    def create_styled_button(text, icon_name=None, parent=None):
        button = QPushButton(text, parent)
        button.setMinimumWidth(AppStyles.BUTTON_MIN_WIDTH)
        button.setMaximumWidth(AppStyles.BUTTON_MAX_WIDTH)
        if icon_name:
            button.setIcon(button.style().standardIcon(getattr(QStyle, icon_name)))
        return button

    @staticmethod
    def create_title_label(text):
        label = QLabel(text)
        title_font = QFont()
        title_font.setPointSize(AppStyles.TITLE_FONT_SIZE)
        title_font.setBold(True)
        label.setFont(title_font)
        return label

    @staticmethod
    def create_separator():
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)
        return separator

    @staticmethod
    def setup_hotkey_table(table):
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.SingleSelection)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        table.verticalHeader().setVisible(False)
        table.setAlternatingRowColors(True)

    @staticmethod
    def setup_env_var_table(table):
        table.setHorizontalHeaderLabels(["Variable", "Value"])
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)

    @staticmethod
    def setup_dialog_window(dialog, title, size, remove_help_button=True):
        dialog.setWindowTitle(title)
        dialog.resize(*size)
        if remove_help_button:
            dialog.setWindowFlags(dialog.windowFlags() & ~Qt.WindowContextHelpButtonHint)

    @staticmethod
    def create_row_layout(label_text, widget, label_min_width=None):
        row_layout = QHBoxLayout()
        label = QLabel(label_text)
        label.setMinimumWidth(label_min_width or AppStyles.LABEL_MIN_WIDTH)
        row_layout.addWidget(label)
        row_layout.addWidget(widget)
        return row_layout

    @staticmethod
    def create_button_layout(save_button, cancel_button):
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        button_layout.addWidget(save_button)
        button_layout.addWidget(cancel_button)
        return button_layout

    @staticmethod
    def setup_env_dialog_ui(dialog):
        layout = QVBoxLayout(dialog)
        layout.setSpacing(AppStyles.DIALOG_SPACING)
        layout.setContentsMargins(*AppStyles.DIALOG_MARGINS)

        env_table = QTableWidget(0, 2)
        AppStyles.setup_env_var_table(env_table)
        layout.addWidget(env_table)

        button_layout = QHBoxLayout()
        button_layout.setSpacing(AppStyles.DIALOG_SPACING)
        add_var_button = AppStyles.create_styled_button("Add", "SP_FileIcon")
        remove_var_button = AppStyles.create_styled_button("Remove", "SP_TrashIcon")
        button_layout.addWidget(add_var_button)
        button_layout.addWidget(remove_var_button)
        button_layout.addStretch()
        layout.addLayout(button_layout)

        layout.addWidget(AppStyles.create_separator())

        save_button = AppStyles.create_styled_button("Save", "SP_DialogSaveButton")
        cancel_button = AppStyles.create_styled_button("Cancel", "SP_DialogCancelButton")
        layout.addLayout(AppStyles.create_button_layout(save_button, cancel_button))

        return env_table, add_var_button, remove_var_button, save_button, cancel_button

    @staticmethod
    def setup_hotkey_dialog_ui(dialog):
        layout = QVBoxLayout(dialog)
        layout.setSpacing(12)
        layout.setContentsMargins(*AppStyles.DIALOG_MARGINS)

        name_edit = QLineEdit()
        layout.addLayout(AppStyles.create_row_layout("Name:", name_edit))

        hotkey_edit = QLineEdit()
        hotkey_edit.setPlaceholderText("Click to record hotkey")
        hotkey_edit.setReadOnly(True)
        layout.addLayout(AppStyles.create_row_layout("Hotkey:", hotkey_edit))

        script_layout = QHBoxLayout()
        script_label = QLabel("Script:")
        script_label.setMinimumWidth(AppStyles.LABEL_MIN_WIDTH)
        script_edit = QLineEdit()
        browse_button = AppStyles.create_styled_button("Browse", "SP_DirOpenIcon")
        browse_button.setMaximumWidth(80)
        script_layout.addWidget(script_label)
        script_layout.addWidget(script_edit)
        script_layout.addWidget(browse_button)
        layout.addLayout(script_layout)

        env_layout = QHBoxLayout()
        env_label = QLabel("Env Vars:")
        env_label.setMinimumWidth(AppStyles.LABEL_MIN_WIDTH)
        env_count_label = QLabel()
        env_button = AppStyles.create_styled_button("Edit", "SP_FileDialogDetailedView")
        env_button.setMaximumWidth(80)
        env_layout.addWidget(env_label)
        env_layout.addWidget(env_count_label)
        env_layout.addStretch()
        env_layout.addWidget(env_button)
        layout.addLayout(env_layout)

        layout.addWidget(AppStyles.create_separator())

        save_button = AppStyles.create_styled_button("Save", "SP_DialogSaveButton")
        cancel_button = AppStyles.create_styled_button("Cancel", "SP_DialogCancelButton")
        layout.addLayout(AppStyles.create_button_layout(save_button, cancel_button))

        return name_edit, hotkey_edit, script_edit, browse_button, env_count_label, env_button, save_button, cancel_button

    @staticmethod
    def setup_main_window_ui(window):
        layout = QVBoxLayout(window)
        layout.setSpacing(AppStyles.DIALOG_SPACING)
        layout.setContentsMargins(*AppStyles.DIALOG_MARGINS)

        header_layout = QHBoxLayout()
        title_label = AppStyles.create_title_label(APP_NAME)
        header_layout.addWidget(title_label)
        header_layout.addStretch()
        global_env_button = AppStyles.create_styled_button("Global Env", "SP_FileDialogDetailedView")
        global_env_button.setMaximumWidth(100)
        header_layout.addWidget(global_env_button)
        layout.addLayout(header_layout)

        hotkey_table = QTableWidget(0, 4)
        hotkey_table.setHorizontalHeaderLabels(["Hotkey", "Name", "Env Vars", "Script Path"])
        AppStyles.setup_hotkey_table(hotkey_table)
        layout.addWidget(hotkey_table)

        button_layout = QHBoxLayout()

        left_buttons = QHBoxLayout()
        add_button = AppStyles.create_styled_button("Add", "SP_FileIcon")
        edit_button = AppStyles.create_styled_button("Edit", "SP_FileDialogDetailedView")
        remove_button = AppStyles.create_styled_button("Remove", "SP_TrashIcon")
        duplicate_button = AppStyles.create_styled_button("Duplicate", "SP_FileDialogDetailedView")
        left_buttons.addWidget(add_button)
        left_buttons.addWidget(edit_button)
        left_buttons.addWidget(remove_button)
        left_buttons.addWidget(duplicate_button)
        left_buttons.addStretch()

        right_buttons = QHBoxLayout()
        logs_button = AppStyles.create_styled_button("Logs", "SP_FileDialogInfoView")
        logs_button.setMaximumWidth(80)
        right_buttons.addWidget(logs_button)

        button_layout.addLayout(left_buttons)
        button_layout.addLayout(right_buttons)
        layout.addLayout(button_layout)

        return (title_label, global_env_button, hotkey_table,
                add_button, edit_button, remove_button, duplicate_button, logs_button)


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
        self.active_hotkeys = {}
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
        self.active_hotkeys.clear()

        for item in self.hotkeys:
            if item.hotkey and item.script_path:
                try:
                    callback = partial(self.run_script, item)
                    keyboard.add_hotkey(item.hotkey, callback, suppress=False)
                    self.active_hotkeys[item.hotkey] = callback
                    count += 1
                except Exception as e:
                    logger.error(f"Failed to register hotkey '{item.hotkey}' for '{item.name}': {e}")
        logger.info(f"Registered {count} hotkeys.")

    def run_script(self, hotkey_item: HotkeyItem):
        logger.info(f"Running script: {hotkey_item.name} ({hotkey_item.hotkey})")
        if not os.path.exists(hotkey_item.script_path):
            logger.error(f"Script not found: {hotkey_item.script_path}")
            return

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_hotkey_name = hotkey_item.name.replace(" ", "_").lower()
        log_filename = f"{LOGS_DIR}/{safe_hotkey_name}_{timestamp}.log"
        try:
            with open(log_filename, 'w') as log_file:
                env = os.environ.copy()
                env.update(self.global_env_vars)
                env.update(hotkey_item.env_vars)
                subprocess.Popen(
                    ["uv", "run", "--script", hotkey_item.script_path],
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
                    env=env,
                    stdout=log_file,
                    stderr=log_file
                )

            QApplication.instance().processEvents()
            keyboard.unhook_all()
            self.register_all_hotkeys()
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

    def duplicate_hotkey(self, index):
        if 0 <= index < len(self.hotkeys):
            original = self.hotkeys[index]
            copy_name = f"{original.name} (Copy)"
            duplicate = HotkeyItem(
                hotkey=original.hotkey,
                script_path=original.script_path,
                name=copy_name,
                env_vars=original.env_vars.copy()
            )
            logger.info(f"Duplicating hotkey: {original.name} -> {duplicate.name}")
            self.hotkeys.append(duplicate)
            self.save_config()
            self.register_all_hotkeys()
            return len(self.hotkeys) - 1
        return -1

    def set_global_env_vars(self, env_vars):
        logger.info(f"Setting {len(env_vars)} global environment variables.")
        self.global_env_vars = env_vars
        self.save_config()


class EnvVarDialog(QDialog):
    def __init__(self, env_vars=None, parent=None):
        super().__init__(parent)
        AppStyles.setup_dialog_window(self, "Environment Variables", AppStyles.ENV_DIALOG_SIZE)
        self.env_vars_initial = env_vars or {}

        self.env_table, self.add_var_button, self.remove_var_button, self.save_button, self.cancel_button = (
            AppStyles.setup_env_dialog_ui(self)
        )

        self.connect_signals()
        self.populate_env_vars()

    def connect_signals(self):
        self.add_var_button.clicked.connect(self.add_env_var)
        self.remove_var_button.clicked.connect(self.remove_env_var)
        self.save_button.clicked.connect(self.accept)
        self.cancel_button.clicked.connect(self.reject)

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
        self.env_table.editItem(self.env_table.item(row, 0) or QTableWidgetItem(""))

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
        AppStyles.setup_dialog_window(self, "Hotkey Configuration", AppStyles.HOTKEY_DIALOG_SIZE)
        self.hotkey_item = hotkey_item or HotkeyItem()
        self.recording = False
        self.pressed_keys = set()

        (self.name_edit, self.hotkey_edit, self.script_edit, self.browse_button,
         self.env_count_label, self.env_button, self.save_button, self.cancel_button) = (
            AppStyles.setup_hotkey_dialog_ui(self)
        )

        self.initialize_values()
        self.connect_signals()

    def initialize_values(self):
        self.name_edit.setText(self.hotkey_item.name)
        self.hotkey_edit.setText(self.hotkey_item.hotkey)
        self.script_edit.setText(self.hotkey_item.script_path)
        self.env_count_label.setText(f"{len(self.hotkey_item.env_vars)} set")

    def connect_signals(self):
        self.hotkey_edit.mousePressEvent = self.start_recording
        self.browse_button.clicked.connect(self.browse_script)
        self.env_button.clicked.connect(self.edit_env_vars)
        self.save_button.clicked.connect(self.accept)
        self.cancel_button.clicked.connect(self.reject)

    def start_recording(self, _):
        if not self.recording:
            self.recording = True
            self.original_hotkey = self.hotkey_edit.text()
            self.hotkey_edit.setText("Press hotkey combination...")
            self.pressed_keys.clear()
            keyboard.unhook_all()
            keyboard.hook(self.on_key_event)

    def on_key_event(self, event):
        if self.recording and event.event_type == keyboard.KEY_DOWN:
            try:
                if event.scan_code == 1:
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

                if self.parent() and hasattr(self.parent(), 'manager'):
                    self.parent().manager.register_all_hotkeys()

            except Exception as e:
                logger.error(f"Error recording hotkey: {e}")
                self.hotkey_edit.setText(self.original_hotkey)
                self.recording = False
                keyboard.unhook(self.on_key_event)

                if self.parent() and hasattr(self.parent(), 'manager'):
                    self.parent().manager.register_all_hotkeys()

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
        AppStyles.setup_dialog_window(self, APP_NAME, AppStyles.MAIN_WINDOW_SIZE, False)
        if ICON_PATH.exists():
            self.setWindowIcon(QIcon(str(ICON_PATH)))
        else:
            logger.warning(f"Icon file not found: {ICON_PATH}")

        (self.title_label, self.global_env_button, self.hotkey_table,
         self.add_button, self.edit_button, self.remove_button, self.duplicate_button, self.logs_button) = (
            AppStyles.setup_main_window_ui(self)
        )

        self.connect_signals()
        self.populate_hotkey_table()

    def connect_signals(self):
        self.global_env_button.clicked.connect(self.edit_global_env_vars)
        self.hotkey_table.doubleClicked.connect(self.edit_hotkey)
        self.add_button.clicked.connect(self.add_hotkey)
        self.edit_button.clicked.connect(self.edit_hotkey)
        self.remove_button.clicked.connect(self.remove_hotkey)
        self.duplicate_button.clicked.connect(self.duplicate_hotkey)
        self.logs_button.clicked.connect(self.open_logs_directory)

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

    def duplicate_hotkey(self):
        row = self.hotkey_table.currentRow()
        if row >= 0:
            new_index = self.manager.duplicate_hotkey(row)
            if new_index >= 0:
                self.populate_hotkey_table()
                self.hotkey_table.selectRow(new_index)
                logger.info(f"Duplicated hotkey at index {row} to index {new_index}")

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
    AppStyles.apply_dark_theme(app)
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