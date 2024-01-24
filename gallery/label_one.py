import sqlite3
import sys

from gallery import model

if __name__ == "__main__":
    model.init()

    conn = sqlite3.connect(model.DB_PATH)
    cursor = conn.cursor()

    # Look up a face without a person
    face_row = cursor.execute(
        "SELECT id, image_id, extracted_path from faces WHERE person_id IS NULL ORDER BY RANDOM() LIMIT 1",
    ).fetchone()
    if not face_row:
        print("No unlabeled faces!")
        sys.exit(0)
    face_id, image_id, extracted_path = face_row

    # look up the image path
    image_row = cursor.execute(
        "SELECT file_path, original_name from image_hashes WHERE id = ?", (image_id,)
    ).fetchone()
    file_path, original_name = image_row

    file_path = model.ORIGINALS_DIR / file_path
    face_path = model.FACES_DIR / extracted_path

    file_path = file_path.resolve()
    face_path = face_path.resolve()

    prompt = f'who is\n\t{face_path} ({original_name})\nin \n\t{file_path}\n? Enter "<hide>" to hide this detected face.\n'

    provided_name = input(prompt)

    if "<hide>" in provided_name:
        print(f"hide face {face_id}")
        cursor.execute(
            "UPDATE faces SET hidden = ? WHERE id = ?",
            (True, face_id),
        )
        conn.commit()
        sys.exit(0)

    fields = provided_name.split(" ")
    fields = [x for f in fields for x in f.split("-")]
    # print(fields)

    perfect_query = "SELECT * from people WHERE name = ? "
    close_query = (
        "SELECT * from people WHERE (name != ?) AND ("
        + " OR ".join("name LIKE ?" for _ in fields)
        + ")"
    )

    # print(perfect_query)
    # print(close_query)

    perfect_rows = cursor.execute(perfect_query, (provided_name,)).fetchall()
    close_rows = cursor.execute(
        close_query, (provided_name,) + tuple(f"%{f}%" for f in fields)
    ).fetchall()

    choice_i = 0
    if perfect_rows + close_rows:
        prompt = "Matches found...make a selection\n"
        if perfect_rows:
            prompt += f"\t0. {provided_name} (perfect_match)\n"
        else:
            prompt += f"\t0. {provided_name} (new person)\n"
        for i, (match_id, match_name) in enumerate(close_rows):
            prompt += f"\t{i+1}. {match_name}\n"

        while True:
            selection = input(prompt)
            try:
                selected_int = int(selection)
            except ValueError as e:
                print(e)
                continue
            if selected_int == 0:
                if perfect_rows:
                    selected_id, _ = perfect_rows[0]
                    model.set_person(
                        conn, face_id, selected_id, model.PERSON_SOURCE_MANUAL
                    )
                else:
                    selected_id = model.new_person(conn, provided_name)
            else:
                selected_id, selected_name = close_rows[i - 1]

            model.set_person(conn, face_id, selected_id, model.PERSON_SOURCE_MANUAL)
            break

    else:
        person_id = model.new_person(conn, provided_name)
        model.set_person(conn, face_id, person_id, model.PERSON_SOURCE_MANUAL)

    cursor.close()
    conn.close()
