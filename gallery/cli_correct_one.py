import sqlite3
import sys

from gallery import model
from gallery import utils
from gallery.model import update_labels

if __name__ == "__main__":
    model.init()

    conn = sqlite3.connect(model.DB_PATH)
    cursor = conn.cursor()

    # Look up a face with an automatically-assigned person
    face_row = cursor.execute(
        """SELECT id, image_id, person_id, extracted_path from faces 
           WHERE person_source = ?
           ORDER BY RANDOM()
           LIMIT 1""",
        (model.PERSON_SOURCE_AUTOMATIC,),
    ).fetchone()
    if not face_row:
        print("No automatically-labeled faces!")
        sys.exit(0)
    face_id, image_id, person_id, extracted_path = face_row

    # look up the person
    name = model.get_person_name(conn, person_id)

    # look up the image path
    image_row = cursor.execute(
        "SELECT file_path, original_name from originals WHERE id = ?", (image_id,)
    ).fetchone()
    file_path, original_name = image_row

    file_path = model.IMAGES_DIR / file_path
    face_path = model.FACES_DIR / extracted_path

    file_path = file_path.resolve()
    face_path = face_path.resolve()

    prompt = f"is this {name}?\n\t{face_path} ({original_name})\nin \n\t{file_path}\n?"

    if utils.input_yn(prompt):
        print(f"marking face {face_id} for person {person_id} as manual")
        model.set_face_person(conn, face_id, person_id, model.PERSON_SOURCE_MANUAL)

    else:
        person_id = utils.input_person_name(conn, "who is it?")
        model.set_face_person(conn, face_id, person_id, model.PERSON_SOURCE_MANUAL)
        model.face_add_excluded_person(conn, face_id, person_id)

    update_labels()
    cursor.close()
    conn.close()
