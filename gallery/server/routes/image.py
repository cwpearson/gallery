from pathlib import Path

from sanic.response import html
from sanic.request import Request
from sanic import Blueprint

from jinja2 import Environment, FileSystemLoader, select_autoescape

from sqlalchemy.orm import Session
from sqlalchemy import select, or_

from gallery import model
from gallery.model import Person, Face, Image

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"

env = Environment(
    loader=FileSystemLoader(TEMPLATES_DIR), autoescape=select_autoescape()
)


bp = Blueprint("image")


@bp.get("/image/<image_id>")
def bp_image(request: Request, image_id: int):
    print(f"at /image/{image_id}")

    with Session(model.get_engine()) as session:
        image = session.scalars(select(Image).where(Image.id == image_id)).one()

        faces_in_image = session.scalars(
            select(Face)
            .where(Face.image_id == image_id)
            .where(or_(Face.hidden == 0, Face.hidden == None))
        ).all()
        faces = []
        for face in faces_in_image:
            if face.person_id is not None:
                person = session.scalars(
                    select(Person).where(Person.id == face.person_id)
                ).one()
                person_name = person.name
            else:
                person_name = None
            faces += [
                {
                    "id": face.id,
                    "src": face.extracted_path,
                    "person_id": face.person_id,
                    "person_name": person_name,
                }
            ]
        hidden_faces = session.scalars(
            select(Face).where(Face.image_id == image_id).where(Face.hidden != 0)
        ).all()
        hidden_faces = [
            {
                "id": face.id,
                "src": face.extracted_path,
                "person_id": face.person_id,
            }
            for face in hidden_faces
        ]

        all_names = [p.name for p in session.scalars(select(Person)).all()]

        template = env.get_template("image.html")

        return html(
            template.render(
                image_id=image_id,
                img_path=image.file_name,
                original_name=image.original_name,
                height=image.height,
                width=image.width,
                img_hash=image.image_hash,
                file_hash=image.file_hash,
                comment=image.comment,
                faces=faces,
                hidden_faces=hidden_faces,
                all_names=all_names,
            )
        )
