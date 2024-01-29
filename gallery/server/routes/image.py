from pathlib import Path

from sanic.response import html
from sanic.request import Request
from sanic import Blueprint

from jinja2 import Environment, FileSystemLoader, select_autoescape

from sqlalchemy.orm import Session
from sqlalchemy import select

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

        faces = session.scalars(select(Face).where(Face.image_id == image_id)).all()
        faces = [
            {
                "id": face.id,
                "src": face.extracted_path,
                "person_id": face.person_id,
            }
            for face in faces
        ]

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
                faces=faces,
            )
        )
