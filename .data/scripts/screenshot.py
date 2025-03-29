#!/usr/bin/env python3
# /// script
# requires-python = ">=3.8"
# dependencies = [
#   "PyQt5>=5.15.0",
#   "Pillow>=9.0.0",
# ]
# ///

import sys
import os
import json
import datetime
from pathlib import Path
from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, QVBoxLayout,
    QHBoxLayout, QFileDialog, QGridLayout, QDialog, QScrollArea,
    QSizePolicy
)
from PyQt5.QtGui import QPainter, QColor, QPen, QPixmap, QCursor, QImage, QIcon
from PyQt5.QtCore import Qt, QPoint, QRect, QSize, pyqtSignal
from PIL import ImageGrab, Image


class DestinationSelector(QDialog):
    def __init__(self, screenshot_path, default_dir, parent=None):
        super().__init__(parent)
        self.screenshot_path = screenshot_path
        self.default_dir = default_dir
        self.config_file = Path.home() / ".screenshot_destinations.json"
        self.destinations = self.load_destinations()
        self.setup_ui()

    def setup_ui(self):
        self.setWindowTitle("Save Screenshot")
        self.setWindowFlags(Qt.Dialog | Qt.WindowStaysOnTopHint)

        main_layout = QVBoxLayout()

        label = QLabel("Select destination folder:")
        main_layout.addWidget(label)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_content = QWidget()
        self.grid_layout = QGridLayout(scroll_content)

        self.add_destination_buttons()

        scroll_area.setWidget(scroll_content)
        main_layout.addWidget(scroll_area)

        button_layout = QHBoxLayout()

        add_btn = QPushButton("Add Destination")
        add_btn.clicked.connect(self.add_destination)
        button_layout.addWidget(add_btn)

        remove_btn = QPushButton("Remove Destination")
        remove_btn.clicked.connect(self.remove_destination)
        button_layout.addWidget(remove_btn)

        main_layout.addLayout(button_layout)

        self.setLayout(main_layout)
        self.resize(400, 300)

        screen_geometry = QApplication.desktop().screenGeometry()
        x = (screen_geometry.width() - self.width()) // 2
        y = (screen_geometry.height() - self.height()) // 2
        self.move(x, y)

    def load_destinations(self):
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r') as f:
                    return json.load(f)
            except:
                pass
        return [str(self.default_dir)]

    def save_destinations(self):
        with open(self.config_file, 'w') as f:
            json.dump(self.destinations, f)

    def add_destination_buttons(self):
        # Clear all existing buttons
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        row = 0
        col = 0
        max_cols = 3

        for dest in self.destinations:
            dest_path = Path(dest)
            btn = QPushButton(dest_path.name)
            btn.setToolTip(dest)
            btn.setMinimumSize(100, 60)
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            btn.clicked.connect(lambda checked, d=dest: self.save_to_destination(d))

            self.grid_layout.addWidget(btn, row, col)

            col += 1
            if col >= max_cols:
                col = 0
                row += 1

        # Update the layout
        self.grid_layout.update()
        QApplication.processEvents()

    def add_destination(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Destination Folder")
        if folder and folder not in self.destinations:
            self.destinations.append(folder)
            self.save_destinations()
            self.add_destination_buttons()
            # Force UI update after adding new destination
            self.adjustSize()
            self.repaint()
            QApplication.processEvents()

    def remove_destination(self):
        if len(self.destinations) <= 1:
            return

        remove_dialog = QDialog(self)
        remove_dialog.setWindowTitle("Remove Destination")
        layout = QVBoxLayout()

        label = QLabel("Select destination to remove:")
        layout.addWidget(label)

        btn_layout = QVBoxLayout()
        for dest in self.destinations:
            if dest != str(self.default_dir):  # Don't allow removing default
                btn = QPushButton(dest)
                btn.clicked.connect(lambda checked, d=dest: self.confirm_remove(d, remove_dialog))
                btn_layout.addWidget(btn)

        layout.addLayout(btn_layout)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(remove_dialog.reject)
        layout.addWidget(cancel_btn)

        remove_dialog.setLayout(layout)
        remove_dialog.exec_()

    def confirm_remove(self, destination, dialog):
        self.destinations.remove(destination)
        self.save_destinations()
        self.add_destination_buttons()
        dialog.accept()
        # Force layout update after removing destination
        self.repaint()
        QApplication.processEvents()

    def save_to_destination(self, destination):
        dest_path = Path(destination)
        if not dest_path.exists():
            dest_path.mkdir(parents=True, exist_ok=True)

        filename = Path(self.screenshot_path).name
        new_path = dest_path / filename

        try:
            os.rename(self.screenshot_path, new_path)
            print(f"Screenshot saved to {new_path}")
        except Exception as e:
            print(f"Error saving to {new_path}: {e}")

        self.accept()


class ScreenshotOverlay(QWidget):
    def __init__(self):
        super().__init__()
        self.start_point = QPoint()
        self.end_point = QPoint()
        self.is_capturing = False
        self.shift_pressed = False
        self.screenshots_dir = Path.home() / ".screenshots"
        self.screenshots_dir.mkdir(exist_ok=True)
        self.setup_ui()
        self.buffer_pixmap = None
        self.prerender_ui()

    def setup_ui(self):
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setCursor(Qt.CrossCursor)

        self.info_label = QLabel(self)
        self.info_label.setStyleSheet("color: white; background-color: rgba(0, 0, 0, 150); padding: 5px;")
        self.info_label.setAlignment(Qt.AlignCenter)
        self.info_label.setFixedSize(250, 80)
        self.info_label.setText("Size: 0 × 0")
        self.info_label.hide()

        screen_size = QApplication.primaryScreen().size()
        self.screen_width = screen_size.width()
        self.screen_height = screen_size.height()
        self.setGeometry(0, 0, self.screen_width, self.screen_height)

        self.border_pen = QPen(QColor(0, 174, 255), 2, Qt.SolidLine)
        self.text_pen = QPen(QColor(255, 255, 255), 1, Qt.SolidLine)
        self.overlay_color = QColor(0, 0, 0, 80)

    def prerender_ui(self):
        self.buffer_pixmap = QPixmap(self.screen_width, self.screen_height)
        self.buffer_pixmap.fill(Qt.transparent)

        painter = QPainter(self.buffer_pixmap)
        painter.fillRect(self.rect(), self.overlay_color)
        painter.end()

        dummy_selection = QRect(100, 100, 200, 150)
        self._draw_selection(dummy_selection, QPainter(self.buffer_pixmap))

    def showEvent(self, event):
        super().showEvent(event)
        QApplication.processEvents()
        self.repaint()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.close()
        elif event.key() == Qt.Key_Shift:
            self.shift_pressed = True
            self.update()

    def keyReleaseEvent(self, event):
        if event.key() == Qt.Key_Shift:
            self.shift_pressed = False
            self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.is_capturing = True
            self.start_point = event.pos()
            self.end_point = event.pos()

            initial_rect = QRect(self.start_point, QSize(1, 1))
            self._draw_selection(initial_rect, QPainter(self.buffer_pixmap))

            self.update_info_label()
            self.info_label.show()

            self.repaint()

    def mouseMoveEvent(self, event):
        if self.is_capturing:
            old_end_point = QPoint(self.end_point)
            self.end_point = event.pos()

            if self.shift_pressed:
                width = abs(self.end_point.x() - self.start_point.x())
                height = abs(self.end_point.y() - self.start_point.y())
                size = max(width, height)

                if self.end_point.x() > self.start_point.x():
                    self.end_point.setX(self.start_point.x() + size)
                else:
                    self.end_point.setX(self.start_point.x() - size)

                if self.end_point.y() > self.start_point.y():
                    self.end_point.setY(self.start_point.y() + size)
                else:
                    self.end_point.setY(self.start_point.y() - size)

            if old_end_point != self.end_point:
                self.update_info_label()
                self.repaint()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.is_capturing:
            self.is_capturing = False
            self.info_label.hide()

            if self.start_point != self.end_point:
                screenshot_path = self.capture_screenshot()
                self.hide()
                QApplication.processEvents()

                selector = DestinationSelector(screenshot_path, self.screenshots_dir)
                selector.exec_()

            self.close()

    def update_info_label(self):
        x1, y1 = self.start_point.x(), self.start_point.y()
        x2, y2 = self.end_point.x(), self.end_point.y()
        width = abs(x2 - x1)
        height = abs(y2 - y1)

        info_text = f"Start: ({x1}, {y1})\nEnd: ({x2}, {y2})\nSize: {width} × {height}"
        self.info_label.setText(info_text)

        if y1 > 100:
            label_y = min(y1, y2) - 90
        else:
            label_y = max(y1, y2) + 10

        label_x = min(x1, x2)
        if label_x + self.info_label.width() > self.width():
            label_x = self.width() - self.info_label.width() - 10

        self.info_label.move(label_x, label_y)

    def _draw_selection(self, selection, painter):
        x, y = selection.x(), selection.y()
        width, height = selection.width(), selection.height()

        painter.setCompositionMode(QPainter.CompositionMode_Clear)
        painter.fillRect(selection, Qt.transparent)

        painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
        painter.setPen(self.border_pen)
        painter.drawRect(selection)

        if width > 1 and height > 1:
            painter.setPen(self.text_pen)
            dimension_text = f"{width} × {height}"
            text_width = painter.fontMetrics().horizontalAdvance(dimension_text)

            text_x = x + (width - text_width) // 2
            if height > 30:
                text_y = y + height - 10
            else:
                text_y = y + height + 20

            painter.drawText(text_x, text_y, dimension_text)

    def paintEvent(self, event):
        if self.buffer_pixmap is None or self.buffer_pixmap.size() != self.size():
            self.buffer_pixmap = QPixmap(self.size())
            self.buffer_pixmap.fill(Qt.transparent)

        buffer = QPixmap(self.buffer_pixmap.size())
        buffer.fill(Qt.transparent)

        buffer_painter = QPainter(buffer)
        buffer_painter.setRenderHint(QPainter.Antialiasing, False)

        buffer_painter.fillRect(self.rect(), self.overlay_color)

        if self.is_capturing:
            x = min(self.start_point.x(), self.end_point.x())
            y = min(self.start_point.y(), self.end_point.y())
            width = abs(self.end_point.x() - self.start_point.x())
            height = abs(self.end_point.y() - self.start_point.y())
            selection = QRect(x, y, width, height)

            self._draw_selection(selection, buffer_painter)

        buffer_painter.end()

        screen_painter = QPainter(self)
        screen_painter.drawPixmap(0, 0, buffer)

    def capture_screenshot(self):
        x1, y1 = min(self.start_point.x(), self.end_point.x()), min(self.start_point.y(), self.end_point.y())
        x2, y2 = max(self.start_point.x(), self.end_point.x()), max(self.start_point.y(), self.end_point.y())

        self.hide()
        QApplication.processEvents()

        screenshot = ImageGrab.grab(bbox=(x1, y1, x2, y2))

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = self.screenshots_dir / f"screenshot_{timestamp}.png"

        screenshot.save(filename)

        clipboard_image = screenshot.convert("RGB")
        qimage = QImage(
            clipboard_image.tobytes(),
            clipboard_image.width,
            clipboard_image.height,
            clipboard_image.width * 3,
            QImage.Format_RGB888
        )
        QApplication.clipboard().setPixmap(QPixmap.fromImage(qimage))

        print(f"Screenshot copied to clipboard (temporarily saved to {filename})")
        return str(filename)


def main():
    app = QApplication(sys.argv)

    app.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    app.setAttribute(Qt.AA_EnableHighDpiScaling, True)

    app.setDesktopSettingsAware(False)

    screenshot_tool = ScreenshotOverlay()

    QApplication.processEvents()

    screenshot_tool.show()

    QApplication.processEvents()

    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())