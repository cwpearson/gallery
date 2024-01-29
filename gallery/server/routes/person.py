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


bp = Blueprint("person")


@bp.get("/person/<person_id>")
def bp_person(request: Request, person_id: int):
    print(f"at /person/{person_id}")

    images_to_show = []
    with Session(model.get_engine()) as session:
        # retrieve the person
        person = session.scalars(select(Person).where(Person.id == person_id)).one()

        # get all faces for this person
        faces = session.scalars(select(Face).where(Face.person_id == person_id)).all()

        # get the image that has this face
        images: list[Image] = []
        for face in faces:
            images += [
                session.scalars(select(Image).where(Image.id == face.image_id)).one()
            ]

        for image in images:
            # get faces from this image that are of this person
            faces_of_person = session.scalars(
                select(Face)
                .where(Face.person_id == person_id)
                .where(Face.image_id == image.id)
            ).all()

            faces_to_show = [
                {
                    "src": fop.extracted_path,
                    "id": fop.id,
                }
                for fop in faces_of_person
            ]

            print(faces_to_show)
            images_to_show += [
                {
                    "src": image.file_name,
                    "id": image.id,
                    "faces": faces_to_show,
                }
            ]

        people = session.scalars(select(Person)).all()
        name_suggestions = [p.name for p in people]

    template = env.get_template("person.html")

    return html(
        template.render(
            person_name=person.name,
            person_id=person.id,
            images=images_to_show,
            name_suggestions=name_suggestions,
        )
    )
