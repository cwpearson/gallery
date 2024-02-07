import sqlite3

from PIL import Image

from gallery import model


def clean_up_null_person_with_source(conn: sqlite3.Connection):
    cursor = conn.cursor()

    face_rows = cursor.execute(
        "SELECT id FROM faces WHERE person_id is NULL AND person_source IS NOT NULL",
    ).fetchall()

    for face_row in face_rows:
        face_id = face_row[0]
        print(f"unset person_source for face {face_id}")
        cursor.execute("UPDATE faces SET person_source = NULL WHERE id = ?", (face_id,))

    cursor.close()


def add_original_image_sizes(conn: sqlite3.Connection):
    cursor = conn.cursor()

    original_rows = cursor.execute(
        "SELECT id, file_path FROM originals WHERE width is NULL OR height is NULL",
    ).fetchall()

    for original_row in original_rows:
        original_id, file_name = original_row[0]
        print(f"set size for original {original_id}")

        with open(model.IMAGES_DIR / file_name, "rb") as f:
            img = Image.open(f)
            width, height = img.size

        cursor.execute(
            "UPDATE original SET width = ?, height = ? WHERE id = ?",
            (
                width,
                height,
                original_id,
            ),
        )

    cursor.close()


if __name__ == "__main__":
    model.init()

    conn = sqlite3.connect(model.DB_PATH)

    clean_up_null_person_with_source(conn)
    add_original_image_sizes(conn)

    conn.close()
