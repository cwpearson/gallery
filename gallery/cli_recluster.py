from sqlalchemy.orm import Session
from sqlalchemy import select

from gallery.model import Face, get_engine, update_labels, init, remove_empty_people

if __name__ == "__main__":
    init()

    with Session(get_engine()) as session:
        # set all automatically-labeled faces to null
        faces = session.scalars(select(Face).where(Face.person_id != None))

        for face in faces:
            face.person_id = None
            face.person_source = None

        remove_empty_people(session)

    update_labels()
