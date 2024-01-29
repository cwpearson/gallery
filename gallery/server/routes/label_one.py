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
    print("at /api/v1/label-one")

    print(request.form)

    face_id = request.form.get("face_id")
    name = request.form.get("name")

    if name:
        with Session(model.get_engine()) as session:
            # Look up a person, or create one if they don't exist
            person = session.scalars(
                select(Person).where(Person.name == name)
            ).one_or_none()
            if person is None:
                person = Person(name=name)
                session.add(person)
                session.commit()

            face = session.scalars(select(Face).where(Face.id == face_id)).one()
            face.person_id = person.id
            face.person_source = model.PERSON_SOURCE_MANUAL
            session.commit()

        cli_add_original.update_labels()

    # redirect back where we sumbitted the post from
    return redirect(request.headers.get("Referer"))
