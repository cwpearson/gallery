from pathlib import Path

from sanic.response import html, redirect
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
        person = session.scalars(
            select(Person).where(Person.id == person_id)
        ).one_or_none()

        if not person:
            print("no such person, redirecting to /people")
            return redirect("/people")

        # get all faces for this person
        # faces = session.scalars(select(Face).where(Face.person_id == person_id)).all()
        faces = [face for face in person.faces if face.hidden == 0]

        # get the image that has this face
        # images: list[Image] = []
        # for face in faces:
        #     images += [
        #         session.scalars(select(Image).where(Image.id == face.image_id)).one()
        #     ]
        images = [face.image for face in faces]
        images = list(set(images))

        for image in images:
            # get faces from this image that are of this person (some images contain two of the same person!)
            faces_of_person = session.scalars(
                select(Face)
                .where(Face.person_id == person_id)
                .where(Face.image_id == image.id)
                .where(Face.hidden == 0)
            ).all()

            faces_to_show = [
                {
                    "src": fop.extracted_path,
                    "id": fop.id,
                }
                for fop in faces_of_person
            ]

            images_to_show += [
                {
                    "src": image.file_name,
                    "id": image.id,
                    "faces": faces_to_show,
                }
            ]

        people = session.scalars(select(Person)).all()
        all_names = [p.name for p in people if p.name]

    template = env.get_template("person.html")

    if person.name:
        display_name = person.name
    else:
        display_name = "Anonymous Person"

    return html(
        template.render(
            person_name=display_name,
            person_id=person.id,
            images=images_to_show,
            all_names=all_names,
        )
    )
