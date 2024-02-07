import sqlite3
import sys

from gallery import model

if __name__ == "__main__":
    model.init()

    conn = sqlite3.connect(model.DB_PATH)

    people = model.get_people(conn)

    for person_id, name in people:
        print(f"{name} ({person_id})")

        faces = model.get_faces_for_person(conn, person_id)

        image_ids = set()

        for face in faces:
            face_id = face[0]
            image_id = face[1]
            image_ids.add(image_id)

        for image_id in image_ids:
            original = model.get_original(conn, image_id)
            path = (model.IMAGES_DIR / original[1]).resolve()
            print(f"\t{path} ({image_id})")

    conn.close()
