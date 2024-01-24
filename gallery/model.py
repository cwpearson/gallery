from pathlib import Path
import multiprocessing
import sqlite3

CPUS = max(multiprocessing.cpu_count() - 1, 1)

CACHE_DIR = Path(__file__).parent / ".." / ".gallery"

ORIGINALS_DIR = CACHE_DIR / "originals"
DB_PATH = CACHE_DIR / "gallery.db"


def init():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS image_hashes (
            id INTEGER PRIMARY KEY,
            sha_hash TEXT,
            file_path TEXT
        )
    """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS image_faces (
            id INTEGER PRIMARY KEY,
            image_id INTEGER,
            top INTEGER,
            right INTEGER,
            bottom INTEGER,
            left INTEGER,
            hidden INTEGER
        )
    """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS faces (
            id INTEGER PRIMARY KEY,
            face_id INTEGER,
            embedding_json TEXT
        )
    """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS face_ (
            id INTEGER PRIMARY KEY,
            face_id INTEGER,
            embedding_json TEXT
        )
    """
    )
