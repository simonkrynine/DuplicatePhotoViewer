from pathlib import Path
from typing import Dict, List
from PIL import Image
import imagehash

from PySide6.QtCore import QThread, Signal

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp", ".tiff"}


class ScanWorker(QThread):
    """
    Background worker that scans a directory for duplicate images.

    Signals:
        progress(int, int)        — (files_scanned, total_files)
        found_duplicate(str, list) — (hash_key, [list of matching file paths])
        finished(int, int)         — (total_files_scanned, total_duplicate_groups)
        error(str)                 — human-readable error message
    """

    progress = Signal(int, int)
    found_duplicate = Signal(str, list)
    finished = Signal(int, int)
    error = Signal(str)

    def __init__(self, directory: str, hash_size: int = 8, threshold: int = 0):
        """
        Args:
            directory:  Root directory to scan (recursive).
            hash_size:  Controls imagehash precision. Higher = more sensitive.
                        8 is a good default.
            threshold:  Maximum Hamming distance to consider images identical.
                        0 = exact perceptual match, 5–10 = near-duplicates.
        """
        super().__init__()
        self.directory = Path(directory)
        self.hash_size = hash_size
        self.threshold = threshold
        self._abort = False

    def abort(self):
        """Call from the main thread to cancel a running scan."""
        self._abort = True

    def run(self):
        try:
            image_files = [
                p for p in self.directory.rglob("*")
                if p.suffix.lower() in SUPPORTED_EXTENSIONS
            ]
        except PermissionError as e:
            self.error.emit(f"Permission denied: {e}")
            return

        total = len(image_files)
        if total == 0:
            self.finished.emit(0, 0)
            return

        # Map hash -> list of paths
        hash_map: Dict[str, List[str]] = {}

        for idx, path in enumerate(image_files):
            if self._abort:
                return

            try:
                img = Image.open(path)
                h = str(imagehash.phash(img, hash_size=self.hash_size))
            except Exception:
                # Skip unreadable files silently
                self.progress.emit(idx + 1, total)
                continue

            if self.threshold == 0:
                # Fast path: exact hash match
                bucket = h
            else:
                # Slow path: find closest existing bucket within threshold
                bucket = self._find_bucket(h, hash_map)

            if bucket not in hash_map:
                hash_map[bucket] = []
            hash_map[bucket].append(str(path))

            self.progress.emit(idx + 1, total)

        # Emit only groups with duplicates
        duplicate_groups = {k: v for k, v in hash_map.items() if len(v) > 1}
        for key, paths in duplicate_groups.items():
            self.found_duplicate.emit(key, paths)

        self.finished.emit(total, len(duplicate_groups))

    def _find_bucket(self, new_hash_str: str, hash_map: Dict[str, List[str]]) -> str:
        """
        For near-duplicate matching, find an existing bucket whose hash is
        within `self.threshold` Hamming distance of new_hash_str.
        Returns the matching bucket key, or new_hash_str if none found.
        """
        new_hash = imagehash.hex_to_hash(new_hash_str)
        for existing_key in hash_map:
            existing_hash = imagehash.hex_to_hash(existing_key)
            if (new_hash - existing_hash) <= self.threshold:
                return existing_key
        return new_hash_str
