from pathlib import Path

from sanic.response import html
from sanic.request import Request
from sanic import Blueprint

from jinja2 import Environment, FileSystemLoader, select_autoescape

from sqlalchemy.orm import Session
from sqlalchemy import select, func

from gallery import model
from gallery.model import Person, Face

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"

env = Environment(
    loader=FileSystemLoader(TEMPLATES_DIR), autoescape=select_autoescape()
)


bp = Blueprint("people")


@bp.get("/people")
def bp_people(request: Request):
    print("at /people")

    with Session(model.get_engine()) as session:
        people = session.scalars(select(Person)).all()

        template = env.get_template("people.html")

        people_counts = session.query(
            Face.person_id, func.count(Face.person_id)
        ).group_by(Face.person_id)

        counts = {id: count for id, count in people_counts}

        people = [
            {"id": person.id, "name": person.name, "count": counts.get(person.id, 0)}
            for person in people
        ]

        return html(
            template.render(
                people=people,
            )
        )
