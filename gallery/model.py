from pathlib import Path
import multiprocessing
import sqlite3
import json
import numpy as np


PERSON_SOURCE_MANUAL = 1
PERSON_SOURCE_AUTOMATIC = 2

CPUS = max(multiprocessing.cpu_count() - 1, 1)

CACHE_DIR = Path(__file__).parent / ".." / ".gallery"

ORIGINALS_DIR = CACHE_DIR / "originals"
FACES_DIR = CACHE_DIR / "faces"
DB_PATH = CACHE_DIR / "gallery.db"


def init():
    DB_PATH.parent.mkdir(exist_ok=True, parents=True)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS image_hashes (
            id INTEGER PRIMARY KEY,
            sha_hash TEXT,
            file_path TEXT,
            original_name TEXT
        )
    """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS faces (
            id INTEGER PRIMARY KEY,
            image_id INTEGER,
            top INTEGER,
            right INTEGER,
            bottom INTEGER,
            left INTEGER,
            hidden INTEGER,
            extracted_path TEXT,
            person_id INTEGER,
            person_source INTEGER,
            embedding_json TEXT
        )
    """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS people (
            id INTEGER PRIMARY KEY,
            name TEXT
        )
    """
    )

    cursor.close()
    conn.close()


def new_person(conn: sqlite3.Connection, name) -> int:
    cursor = conn.cursor()
    print(f"new person {name}")
    cursor.execute(
        "INSERT INTO people (name) VALUES (?)",
        (name,),
    )
    conn.commit()
    return cursor.lastrowid


def all_embeddings(conn: sqlite3.Connection, include_hidden=False) -> list:
    cursor = conn.cursor()
    query = "SELECT id, embedding_json FROM faces"
    if not include_hidden:
        query += " WHERE hidden = 0"
    face_rows = cursor.execute(query).fetchall()
    cursor.close()
    return [json.loads(embedding_json) for id, embedding_json in face_rows], [
        id for id, embedding_json in face_rows
    ]


def get_person(conn: sqlite3.Connection, face_id):
    """
    return person_id, person_source for face_id
    """

    cursor = conn.cursor()
    # print(f"get_person({face_id})")
    face_rows = cursor.execute(
        "SELECT person_id, person_source FROM faces WHERE id = ?", (face_id,)
    ).fetchone()
    cursor.close()

    person_id, person_source = face_rows
    return person_id, person_source


def set_person(conn: sqlite3.Connection, face_id, person_id, person_source: int):
    cursor = conn.cursor()
    print(f"set face {face_id} to person {person_id}")
    cursor.execute(
        "UPDATE faces SET person_id = ?, person_source = ? WHERE id = ?",
        (person_id, person_source, face_id),
    )
    conn.commit()
