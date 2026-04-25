import os
from pathlib import Path
from typing import List

from PIL import Image as PILImage
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap, QImage
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel,
    QCheckBox, QFrame, QSizePolicy
)

THUMB_SIZE = 140


def pil_to_qpixmap(pil_img: PILImage.Image, size: int) -> QPixmap:
    pil_img = pil_img.convert("RGBA")
    pil_img.thumbnail((size, size), PILImage.LANCZOS)
    data = pil_img.tobytes("raw", "RGBA")
    qimg = QImage(data, pil_img.width, pil_img.height, QImage.Format.Format_RGBA8888)
    return QPixmap.fromImage(qimg)


class ThumbnailCard(QFrame):
    """A single image card with thumbnail, filename, size, and a delete checkbox."""

    selection_changed = Signal()

    def __init__(self, file_path: str, protected: bool = False, parent=None):
        super().__init__(parent)
        self.file_path = file_path
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setFixedWidth(THUMB_SIZE + 24)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        self.setStyleSheet("""
            ThumbnailCard {
                background: #2a2a2a;
                border: 1px solid #3a3a3a;
                border-radius: 6px;
            }
            ThumbnailCard:hover {
                border-color: #555;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)

        # Thumbnail
        self.thumb_label = QLabel()
        self.thumb_label.setFixedSize(THUMB_SIZE, THUMB_SIZE)
        self.thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumb_label.setStyleSheet("background: #1a1a1a; border-radius: 4px;")
        layout.addWidget(self.thumb_label)

        # Load thumbnail
        try:
            img = PILImage.open(file_path)
            pixmap = pil_to_qpixmap(img, THUMB_SIZE)
            self.thumb_label.setPixmap(pixmap)
        except Exception:
            self.thumb_label.setText("⚠ unreadable")
            self.thumb_label.setStyleSheet("color: #888; font-size: 11px; background: #1a1a1a;")

        # Filename
        name = Path(file_path).name
        name_label = QLabel(name)
        name_label.setWordWrap(True)
        name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name_label.setStyleSheet("color: #ccc; font-size: 11px;")
        name_label.setToolTip(file_path)
        layout.addWidget(name_label)

        # File size
        try:
            size_bytes = os.path.getsize(file_path)
            size_str = self._format_size(size_bytes)
        except OSError:
            size_str = "unknown"
        size_label = QLabel(size_str)
        size_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        size_label.setStyleSheet("color: #666; font-size: 10px;")
        layout.addWidget(size_label)

        # Delete checkbox
        if protected:
            self.checkbox = QCheckBox("Keep (protected)")
            self.checkbox.setEnabled(False)
            self.checkbox.setStyleSheet("""
                QCheckBox { color: #557755; font-size: 12px; font-weight: bold; }
                QCheckBox::indicator { width: 18px; height: 18px; }
            """)
        else:
            self.checkbox = QCheckBox("Mark for deletion")
            self.checkbox.setStyleSheet("""
                QCheckBox { color: #e05555; font-size: 12px; font-weight: bold; }
                QCheckBox::indicator { width: 18px; height: 18px; }
                QCheckBox::indicator:unchecked { border: 2px solid #883333; border-radius: 3px; background: #1a1a1a; }
                QCheckBox::indicator:checked { border: 2px solid #e05555; border-radius: 3px; background: #e05555; }
            """)
            self.checkbox.stateChanged.connect(lambda _: self.selection_changed.emit())
        layout.addWidget(self.checkbox, alignment=Qt.AlignmentFlag.AlignHCenter)

    def is_marked(self) -> bool:
        return self.checkbox.isChecked()

    @staticmethod
    def _format_size(n: int) -> str:
        for unit in ("B", "KB", "MB", "GB"):
            if n < 1024:
                return f"{n:.0f} {unit}"
            n /= 1024
        return f"{n:.1f} TB"


class DuplicateGroupWidget(QFrame):
    """
    Displays a horizontal row of ThumbnailCards for one duplicate group.
    Shows a group header with the duplicate count.
    """

    deletion_changed = Signal()

    def __init__(self, paths: List[str], group_number: int, parent=None):
        super().__init__(parent)
        self.paths = paths
        self.setStyleSheet("""
            DuplicateGroupWidget {
                background: #222;
                border: 1px solid #333;
                border-radius: 8px;
            }
        """)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 10, 12, 10)
        outer.setSpacing(8)

        # Header
        header = QLabel(f"Group {group_number}  ·  {len(paths)} duplicates")
        header.setStyleSheet("color: #888; font-size: 11px; font-weight: bold; letter-spacing: 1px;")
        outer.addWidget(header)

        # Thumbnails row
        row = QHBoxLayout()
        row.setSpacing(10)
        row.setAlignment(Qt.AlignmentFlag.AlignLeft)

        self.cards: List[ThumbnailCard] = []
        for i, path in enumerate(paths):
            card = ThumbnailCard(path, protected=(i == 0))
            card.selection_changed.connect(self.deletion_changed.emit)
            self.cards.append(card)
            row.addWidget(card)

        row.addStretch()
        outer.addLayout(row)

    def marked_paths(self) -> List[str]:
        return [c.file_path for c in self.cards if c.is_marked()]
