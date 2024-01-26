from pathlib import Path
import multiprocessing
import sqlite3
import json
import numpy as np
from typing import Tuple


PERSON_SOURCE_MANUAL = 1
PERSON_SOURCE_AUTOMATIC = 2

HIDDEN_REASON_SMALL = 1
HIDDEN_REASON_MANUAL = 2

CPUS = max(multiprocessing.cpu_count() - 1, 1)

CACHE_DIR = Path(__file__).parent / ".." / ".gallery"

ORIGINALS_DIR = CACHE_DIR / "originals"
FACES_DIR = CACHE_DIR / "faces"
DB_PATH = CACHE_DIR / "gallery.db"


def init():
    DB_PATH.parent.mkdir(exist_ok=True, parents=True)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # img_hash: hash of the image data
    # file_hash: hash of the file bytes
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS originals (
            id INTEGER PRIMARY KEY,
            file_path TEXT,
            original_name TEXT,
            height INT,
            width INT,
            img_hash TEXT,
            file_hash TEXT
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
            hidden_reason INTEGER,
            extracted_path TEXT,
            person_id INTEGER,
            person_source INTEGER,
            excluded_people TEXT,
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


def get_face_person(conn: sqlite3.Connection, face_id):
    """
    return person_id, person_source for face_id
    """

    cursor = conn.cursor()
    # print(f"get_face_person({face_id})")
    face_rows = cursor.execute(
        "SELECT person_id, person_source FROM faces WHERE id = ?", (face_id,)
    ).fetchone()
    cursor.close()

    person_id, person_source = face_rows
    return person_id, person_source


def set_face_person(conn: sqlite3.Connection, face_id, person_id, person_source: int):
    cursor = conn.cursor()
    print(f"set face {face_id} to person {person_id}")
    cursor.execute(
        "UPDATE faces SET person_id = ?, person_source = ? WHERE id = ?",
        (person_id, person_source, face_id),
    )
    conn.commit()


def get_person_name(conn: sqlite3.Connection, person_id: int) -> Tuple[str, None]:
    """return name for person_id"""

    cursor = conn.cursor()
    face_row = cursor.execute(
        "SELECT name FROM people WHERE id = ?", (person_id,)
    ).fetchone()
    cursor.close()

    if face_row:
        return face_row[0]
    else:
        return None


def face_add_excluded_person(conn: sqlite3.Connection, face_id: int, person_id: int):
    cursor = conn.cursor()
    face_row = cursor.execute(
        "SELECT id, excluded_people FROM faces WHERE id = ?",
        (face_id,),
    ).fetchone()

    _, excluded_people_str = face_row

    if excluded_people_str:
        excluded_people = json.loads(excluded_people_str)
    else:
        excluded_people = []
    excluded_people += [person_id]
    excluded_people = list(set(excluded_people))  # uniqify
    print(excluded_people)

    face_row = cursor.execute(
        "UPDATE faces SET excluded_people = ? WHERE id = ?",
        (json.dumps(excluded_people), face_id),
    )
    conn.commit()
    cursor.close()


def get_person_by_name_exact(conn: sqlite3.Connection, name: str) -> int:
    "get the id of the person whose name matches exactly. None if no such person"
    cursor = conn.cursor()
    person_row = cursor.execute(
        "SELECT id FROM people WHERE name = ?",
        (name,),
    ).fetchone()
    cursor.close()

    if person_row is None:
        return person_row
    else:
        return person_row[0]


def get_people_by_name_near(conn: sqlite3.Connection, name: str):
    cursor = conn.cursor()
    fields = name.split(" ")
    fields = [x for f in fields for x in f.split("-")]

    query = (
        "SELECT id, name FROM people WHERE (name != ?) AND ("
        + " OR ".join("name LIKE ?" for _ in fields)
        + ")"
    )

    people_rows = cursor.execute(
        query, (name,) + tuple(f"%{f}%" for f in fields)
    ).fetchall()

    return [id for id, _ in people_rows], [name for _, name in people_rows]


def get_people(conn: sqlite3.Connection) -> list:
    cursor = conn.cursor()
    rows = cursor.execute("SELECT * FROM people").fetchall()
    cursor.close()
    return rows


def get_faces_for_person(conn: sqlite3.Connection, person_id: int) -> list:
    cursor = conn.cursor()
    if person_id is None:
        rows = cursor.execute(
            "SELECT * FROM faces WHERE person_id IS NULL AND hidden = 0"
        ).fetchall()
    else:
        rows = cursor.execute(
            "SELECT * FROM faces WHERE person_id = ? AND hidden = 0", (person_id,)
        ).fetchall()
    cursor.close()
    return rows


def get_original(conn: sqlite3.Connection, original_id: int) -> list:
    cursor = conn.cursor()
    row = cursor.execute(
        "SELECT * FROM originals WHERE id = ?", (original_id,)
    ).fetchone()
    cursor.close()
    return row


def get_originals_for_person(conn: sqlite3.Connection, person_id: int) -> list:
    faces = get_faces_for_person(conn, person_id)

    image_ids = set()

    for face in faces:
        image_id = face[1]
        image_ids.add(image_id)

    originals = []
    for image_id in image_ids:
        originals += [get_original(conn, image_id)]

    return originals


def set_face_hidden(
    conn: sqlite3.Connection, face_id, hidden: bool, hidden_reason: int
):
    cursor = conn.cursor()
    print(f"set face {face_id} hidden={hidden} hidden_reason={hidden_reason}")
    cursor.execute(
        "UPDATE faces SET hidden = ?, hidden_reason = ? WHERE id = ?",
        (hidden, hidden_reason, face_id),
    )
    conn.commit()
    cursor.close()
