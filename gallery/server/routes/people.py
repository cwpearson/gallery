from pathlib import Path

from sanic.response import html
from sanic.request import Request
from sanic import Blueprint

from jinja2 import Environment, FileSystemLoader, select_autoescape

from sqlalchemy.orm import Session
from sqlalchemy import select

from gallery import model
from gallery.model import Person

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"

env = Environment(
    loader=FileSystemLoader(TEMPLATES_DIR), autoescape=select_autoescape()
)


bp = Blueprint("people")


@bp.get("/people")
def bp_people(request: Request):
    print("at /people")

    # retrieve all unlabeled faces
    with Session(model.get_engine()) as session:
        people = session.scalars(select(Person)).all()

        template = env.get_template("people.html")
        return html(
            template.render(
                people=people,
            )
        )
