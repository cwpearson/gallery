from pathlib import Path

from sanic.response import html
from sanic.request import Request
from sanic import Blueprint

from jinja2 import Environment, FileSystemLoader, select_autoescape

from sqlalchemy.orm import Session
from sqlalchemy import select, or_

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

    limit = int(request.args.get("limit", 25))
    offset = int(request.args.get("offset", 0))
    print(f"limit={limit} offset={offset}")
    next_offset = offset + limit
    prev_offset = max(0, offset - limit)
    next_limit = limit
    prev_limit = limit

    # retrieve all faces that are unlabele
    with Session(model.get_engine()) as session:
        faces = session.scalars(
            select(Face)
            .where(Face.hidden == False)
            .where(
                or_(
                    Face.person_id == None,
                    Face.person_source == model.PERSON_SOURCE_AUTOMATIC,
                )
            )
            .offset(offset)
            .limit(limit)
        ).all()

        # for each unlabeled face, retrieve the image the face is from
        records = []
        for face in faces:
            image = session.scalars(
                select(Image).where(Image.id == face.image_id)
            ).one()
            records += [
                {
                    "face_id": face.id,
                    "face_src": face.extracted_path,
                    "image_id": image.id,
                    "image_src": image.file_name,
                    "image_title": model.get_image_title(session, image.id),
                }
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
            prev_offset=prev_offset,
            prev_limit=prev_limit,
            next_offset=next_offset,
            next_limit=next_limit,
        )
    )
