from pathlib import Path

from sanic.response import redirect
from sanic.request import Request
from sanic import Blueprint

from jinja2 import Environment, FileSystemLoader, select_autoescape

from sqlalchemy.orm import Session
from sqlalchemy import select

from gallery import model
from gallery.model import Person, Face

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"

env = Environment(
    loader=FileSystemLoader(TEMPLATES_DIR), autoescape=select_autoescape()
)


bp = Blueprint("label-many")


@bp.post("/api/v1/label-many")
def bp_label_one(request: Request):
    print("at /api/v1/label-many")

    print(request.form.items())

    with Session(model.get_engine()) as session:
        for k in request.form.keys():
            v = request.form.get(k)
            sep = k.find("-")
            face_id = int(k[:sep])
            field = k[sep + 1 :]
            print(face_id, field, v)

            if field == "name" and v:
                person = session.scalars(
                    select(Person).where(Person.name == v)
                ).one_or_none()
                if person is None:
                    person = Person(name=v)
                    session.add(person)
                    session.commit()
                face = session.scalars(select(Face).where(Face.id == face_id)).one()
                face.person_id = person.id
                face.person_source = model.PERSON_SOURCE_MANUAL
                print(f"set face {face.id} to person {person.id}")
                session.commit()
            if field == "hidden" and v == "on":
                face = session.scalars(select(Face).where(Face.id == face_id)).one()
                face.hidden = True
                face.hidden_reason = model.HIDDEN_REASON_MANUAL
                session.commit()

    model.update_labels()

    return redirect(request.headers.get("referer"))
