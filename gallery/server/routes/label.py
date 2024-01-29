from pathlib import Path

from sanic.response import html
from sanic.request import Request
from sanic import Blueprint

from jinja2 import Environment, FileSystemLoader, select_autoescape

from sqlalchemy.orm import Session
from sqlalchemy import select

from gallery import model
from gallery.model import Face, Image, Person

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"

env = Environment(
    loader=FileSystemLoader(TEMPLATES_DIR), autoescape=select_autoescape()
)


bp = Blueprint("label")


@bp.get("/label")
def bp_label(request: Request):
    print("at /label")

    # retrieve all unlabeled faces
    with Session(model.get_engine()) as session:
        faces = session.scalars(
            select(Face).where(Face.person_id == None).where(Face.hidden == False)
        ).all()

        # for each unlabeled face, retrieve the image the face is from
        records = []
        for face in faces:
            image = session.scalars(
                select(Image).where(Image.id == face.image_id)
            ).one()
            records += [
                (face.id, face.extracted_path, image.file_name, image.original_name)
            ]

    print(f"handle_label: {len(records)} records")

    with Session(model.get_engine()) as session:
        people = session.scalars(select(Person)).all()
        name_suggestions = [p.name for p in people]

    template = env.get_template("label.html")
    return html(
        template.render(
            records=records,
            name_suggestions=name_suggestions,
        )
    )
