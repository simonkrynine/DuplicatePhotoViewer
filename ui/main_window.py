import send2trash
from typing import List

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QProgressBar, QFileDialog,
    QScrollArea, QFrame, QSpinBox, QMessageBox,
    QSizePolicy, QStatusBar
)

from core.scanner import ScanWorker
from ui.duplicate_group import DuplicateGroupWidget


DARK = """
QMainWindow, QWidget#root {
    background: #1a1a1a;
}
QLabel { color: #ddd; }
QPushButton {
    background: #2e2e2e;
    color: #ddd;
    border: 1px solid #444;
    border-radius: 5px;
    padding: 6px 16px;
    font-size: 13px;
}
QPushButton:hover { background: #3a3a3a; border-color: #666; }
QPushButton:pressed { background: #252525; }
QPushButton:disabled { color: #555; border-color: #333; }
QPushButton#danger {
    background: #5a1e1e;
    border-color: #8b3a3a;
    color: #ffaaaa;
}
QPushButton#danger:hover { background: #6e2424; }
QPushButton#danger:disabled { background: #2e2020; color: #554444; }
QProgressBar {
    background: #2a2a2a;
    border: 1px solid #3a3a3a;
    border-radius: 4px;
    height: 8px;
    text-align: center;
    color: transparent;
}
QProgressBar::chunk { background: #4a90d9; border-radius: 3px; }
QSpinBox {
    background: #2a2a2a;
    color: #ddd;
    border: 1px solid #444;
    border-radius: 4px;
    padding: 4px 8px;
}
QScrollArea { border: none; background: transparent; }
QScrollBar:vertical {
    background: #1e1e1e;
    width: 8px;
    border-radius: 4px;
}
QScrollBar::handle:vertical {
    background: #444;
    border-radius: 4px;
    min-height: 30px;
}
QStatusBar { color: #666; font-size: 11px; background: #161616; }
"""


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Image Deduplicator")
        self.setMinimumSize(860, 600)
        self.resize(1100, 700)
        self.setStyleSheet(DARK)

        self._worker: ScanWorker | None = None
        self._group_widgets: List[DuplicateGroupWidget] = []
        self._group_count = 0

        # ── Root widget ──────────────────────────────────────────────────────
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(16, 14, 16, 8)
        layout.setSpacing(10)

        # ── Toolbar ──────────────────────────────────────────────────────────
        toolbar = QHBoxLayout()
        toolbar.setSpacing(10)

        self.dir_label = QLabel("No folder selected")
        self.dir_label.setStyleSheet("color: #888; font-size: 12px;")
        self.dir_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        self.pick_btn = QPushButton("📂  Choose Folder")
        self.pick_btn.clicked.connect(self._pick_directory)

        threshold_label = QLabel("Threshold:")
        threshold_label.setStyleSheet("color: #888; font-size: 12px;")
        self.threshold_spin = QSpinBox()
        self.threshold_spin.setRange(0, 20)
        self.threshold_spin.setValue(0)
        self.threshold_spin.setToolTip(
            "Hamming distance threshold.\n"
            "0 = exact perceptual match only.\n"
            "Higher values catch near-duplicates (resized, recompressed)."
        )

        self.scan_btn = QPushButton("🔍  Scan")
        self.scan_btn.clicked.connect(self._start_scan)
        self.scan_btn.setEnabled(False)

        self.cancel_btn = QPushButton("✕  Cancel")
        self.cancel_btn.clicked.connect(self._cancel_scan)
        self.cancel_btn.setEnabled(False)

        toolbar.addWidget(self.pick_btn)
        toolbar.addWidget(self.dir_label)
        toolbar.addWidget(threshold_label)
        toolbar.addWidget(self.threshold_spin)
        toolbar.addWidget(self.scan_btn)
        toolbar.addWidget(self.cancel_btn)
        layout.addLayout(toolbar)

        # ── Progress bar ─────────────────────────────────────────────────────
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        # ── Results scroll area ───────────────────────────────────────────────
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.results_container = QWidget()
        self.results_layout = QVBoxLayout(self.results_container)
        self.results_layout.setContentsMargins(0, 0, 0, 0)
        self.results_layout.setSpacing(10)
        self.results_layout.addStretch()

        self.scroll.setWidget(self.results_container)
        layout.addWidget(self.scroll, stretch=1)

        # ── Bottom action bar ─────────────────────────────────────────────────
        action_bar = QHBoxLayout()
        action_bar.setSpacing(10)

        self.marked_label = QLabel("")
        self.marked_label.setStyleSheet("color: #888; font-size: 12px;")

        self.delete_btn = QPushButton("🗑  Delete Marked Files")
        self.delete_btn.setObjectName("danger")
        self.delete_btn.setEnabled(False)
        self.delete_btn.clicked.connect(self._delete_marked)

        action_bar.addWidget(self.marked_label)
        action_bar.addStretch()
        action_bar.addWidget(self.delete_btn)
        layout.addLayout(action_bar)

        # ── Status bar ────────────────────────────────────────────────────────
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self._set_status("Ready")

        # Placeholder message
        self._show_placeholder("Choose a folder and click Scan to find duplicate images.")

    # ── Directory picker ──────────────────────────────────────────────────────

    def _pick_directory(self):
        path = QFileDialog.getExistingDirectory(self, "Select Image Folder")
        if path:
            self._directory = path
            # Truncate long paths for display
            display = path if len(path) <= 70 else "…" + path[-67:]
            self.dir_label.setText(display)
            self.dir_label.setToolTip(path)
            self.scan_btn.setEnabled(True)

    # ── Scan lifecycle ─────────────────────────────────────────────────────────

    def _start_scan(self):
        self._clear_results()
        self.progress.setValue(0)
        self.progress.setVisible(True)
        self.scan_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.delete_btn.setEnabled(False)
        self.marked_label.setText("")
        self._group_count = 0
        self._show_placeholder("")

        self._worker = ScanWorker(
            directory=self._directory,
            threshold=self.threshold_spin.value()
        )
        self._worker.progress.connect(self._on_progress)
        self._worker.found_duplicate.connect(self._on_duplicate_found)
        self._worker.finished.connect(self._on_scan_finished)
        self._worker.error.connect(self._on_scan_error)
        self._worker.start()
        self._set_status("Scanning…")

    def _cancel_scan(self):
        if self._worker:
            self._worker.abort()
        self._set_scan_idle()
        self._set_status("Scan cancelled.")

    # ── Worker slots ──────────────────────────────────────────────────────────

    @Slot(int, int)
    def _on_progress(self, done: int, total: int):
        self.progress.setMaximum(total)
        self.progress.setValue(done)
        self._set_status(f"Scanning… {done} / {total} files")

    @Slot(str, list)
    def _on_duplicate_found(self, key: str, paths: list):
        self._group_count += 1
        widget = DuplicateGroupWidget(paths, self._group_count)
        widget.deletion_changed.connect(self._refresh_delete_bar)
        self._group_widgets.append(widget)

        # Insert before the trailing stretch
        idx = self.results_layout.count() - 1
        self.results_layout.insertWidget(idx, widget)

        # Add a thin separator
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("color: #2e2e2e;")
        self.results_layout.insertWidget(idx + 1, line)

    @Slot(int, int)
    def _on_scan_finished(self, total: int, groups: int):
        self._set_scan_idle()
        if groups == 0:
            self._show_placeholder("✅  No duplicates found.")
            self._set_status(f"Scan complete — {total} files checked, no duplicates found.")
        else:
            self._set_status(
                f"Scan complete — {total} files checked, {groups} duplicate group(s) found."
            )

    @Slot(str)
    def _on_scan_error(self, message: str):
        self._set_scan_idle()
        self._show_placeholder(f"⚠  Error: {message}")
        self._set_status(f"Error: {message}")

    # ── Delete ─────────────────────────────────────────────────────────────────

    def _refresh_delete_bar(self):
        marked = self._all_marked_paths()
        if marked:
            self.marked_label.setText(f"{len(marked)} file(s) marked for deletion")
            self.delete_btn.setEnabled(True)
        else:
            self.marked_label.setText("")
            self.delete_btn.setEnabled(False)

    def _delete_marked(self):
        paths = self._all_marked_paths()
        if not paths:
            return

        reply = QMessageBox.warning(
            self,
            "Confirm",
            f"Move {len(paths)} file(s) to the Recycle Bin?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        errors = []
        moved = 0
        for path in paths:
            try:
                send2trash.send2trash(path)
                moved += 1
            except Exception as e:
                errors.append(f"{path}: {e}")

        if errors:
            QMessageBox.critical(self, "Move Errors", "\n".join(errors))

        self._set_status(f"{moved} file(s) moved to Recycle Bin.")
        self._clear_results()
        self._show_placeholder("Files moved to Recycle Bin. Run a new scan to refresh results.")
        self.delete_btn.setEnabled(False)
        self.marked_label.setText("")

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _all_marked_paths(self) -> List[str]:
        paths = []
        for gw in self._group_widgets:
            paths.extend(gw.marked_paths())
        return paths

    def _clear_results(self):
        self._group_widgets.clear()
        while self.results_layout.count() > 1:
            item = self.results_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _show_placeholder(self, text: str):
        # Replace any existing placeholder
        item = self.results_layout.itemAt(self.results_layout.count() - 1)
        if item and item.widget() and item.widget().objectName() == "placeholder":
            item.widget().deleteLater()
            self.results_layout.takeAt(self.results_layout.count() - 1)

        if text:
            label = QLabel(text)
            label.setObjectName("placeholder")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setStyleSheet("color: #555; font-size: 14px; padding: 40px;")
            self.results_layout.addWidget(label)

    def _set_scan_idle(self):
        self.progress.setVisible(False)
        self.scan_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)

    def _set_status(self, message: str):
        self.status_bar.showMessage(message)
