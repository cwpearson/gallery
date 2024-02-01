from pathlib import Path

from sanic.response import html
from sanic.request import Request
from sanic import Blueprint

from jinja2 import Environment, FileSystemLoader, select_autoescape

from sqlalchemy.orm import Session
from sqlalchemy import select, func, or_, desc

from gallery import model
from gallery.model import Person, Face

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"

env = Environment(
    loader=FileSystemLoader(TEMPLATES_DIR), autoescape=select_autoescape()
)


bp = Blueprint("new-people")


@bp.get("/new_people")
def bp_new_people(request: Request):
    print("at /new_people")

    limit = int(request.args.get("limit", 25))
    offset = int(request.args.get("offset", 0))
    print(f"limit={limit} offset={offset}")
    next_offset = offset + limit
    prev_offset = max(0, offset - limit)
    next_limit = limit
    prev_limit = limit

    with Session(model.get_engine()) as session:
        faces_count_subquery = (
            select(Face.person_id, func.count(Face.person_id).label("face_count"))
            .where(Face.hidden == 0)
            .group_by(Face.person_id)
            .subquery()
        )

        # Query the Person table, join with the faces_count_subquery,
        # and sort by the face count
        people_with_face_counts = (
            select(Person, faces_count_subquery.c.face_count)
            .join(
                faces_count_subquery,
                Person.id == faces_count_subquery.c.person_id,
                isouter=True,
            )
            .where(or_(Person.name == "", Person.name == None))
            .order_by(desc(faces_count_subquery.c.face_count))
            .limit(limit)
            .offset(offset)
        )

        # Execute the query
        results = session.execute(people_with_face_counts).fetchall()

        people_data = []
        for person, count in results:
            unhidden_faces = [face for face in person.faces if face.hidden == 0]

            people_data += [
                {
                    "id": person.id,
                    "count": count,
                    "thumb_src": unhidden_faces[0].extracted_path,
                }
            ]

        people_data = sorted(people_data, key=lambda pd: pd["count"], reverse=True)

        named_people = session.scalars(
            select(Person).where(Person.name != None).where(Person.name != "")
        ).all()
        all_names = [p.name for p in named_people if p.name]

        template = env.get_template("new_people.html")
        return html(
            template.render(
                people=people_data,
                all_names=all_names,
                next_limit=next_limit,
                next_offset=next_offset,
                prev_limit=prev_limit,
                prev_offset=prev_offset,
            )
        )
