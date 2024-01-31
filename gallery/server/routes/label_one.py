from pathlib import Path

from sanic.response import redirect
from sanic.request import Request
from sanic import Blueprint

from jinja2 import Environment, FileSystemLoader, select_autoescape

from sqlalchemy.orm import Session
from sqlalchemy import select

from gallery import model
from gallery.model import Face, Person
from gallery import cli_add_original

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"

env = Environment(
    loader=FileSystemLoader(TEMPLATES_DIR), autoescape=select_autoescape()
)


bp = Blueprint("label-one")


@bp.post("/api/v1/label-one")
def bp_label_one(request: Request):
    """
    Assign face `face_id` to person `name`

    In order of preference
    1. name is already a person -> assign this face to that person
    2. face is already a person, and that person has no name -> update that anonymous person to this name
    3. Create a new person with the name and assign this face to that name

    """
    print("at /api/v1/label-one")

    name = request.form.get("name")

    if not name:
        return redirect(request.headers.get("Referer"))

    with Session(model.get_engine()) as session:
        face_id = request.form.get("face_id")
        face = session.scalars(select(Face).where(Face.id == face_id)).one()

        # Look up a person with this exact name
        person_with_name = session.scalars(
            select(Person).where(Person.name == name)
        ).one_or_none()

        # if there is already a person with this name, label this face as that person
        if person_with_name:
            face.person_id = person_with_name.id
            face.person_source = model.PERSON_SOURCE_MANUAL
            session.commit()
            print(
                f"labeled face id={face.id} as existing person id={person_with_name.id}"
            )

        # if this face already has a person, and that person is anonymous, rename that person and mark this label as manual
        elif face.person:
            if not face.person.name:
                face.person.name = name
                face.person_source = model.PERSON_SOURCE_MANUAL
                session.commit()
                print(f"renamed anonymous person id={face.person.id} to {name}")
            else:  # if this face is labeled as a named person, relabel it as a new person with the correct name
                person = Person(name=name)
                session.add(person)
                session.commit()
                face.person = person
                face.person_source = model.PERSON_SOURCE_MANUAL
                session.commit()
                print(f"labeled face {face.id} as new person id={person.id}")

        # make a new person and label the face as that person
        else:
            person = Person(name=name)
            session.add(person)
            session.commit()
            face.person = person
            face.person_source = model.PERSON_SOURCE_MANUAL
            session.commit()
            print(f"labeled face {face.id} as new person id={person.id}")

    model.update_labels()

    # redirect back where we sumbitted the post from
    referer = request.headers.get("Referer")
    print(f"redirect to referer {referer}")
    return redirect(referer)
