from sanic.response import redirect
from sanic.request import Request
from sanic import Blueprint

from sqlalchemy.orm import Session
from sqlalchemy import select

from gallery import model
from gallery.model import Person


bp = Blueprint("name-person")


@bp.post("/api/v1/name-person")
def bp_name_person(request: Request):
    """ """

    print(f"at /api/v1/name-person")

    person_id = int(request.form.get("id"))
    name = request.form.get("name")
    redirect_to = request.headers.get("referer")

    with Session(model.get_engine()) as session:
        person_with_name = session.scalars(
            select(Person).where(Person.name == name)
        ).one_or_none()
        person = session.scalars(select(Person).where(Person.id == person_id)).one()

        if person_with_name:
            model.merge_people(session, person_with_name, person)
            print(f"redirecting to {redirect_to}")
            return redirect(redirect_to)
        else:
            person = session.scalars(select(Person).where(Person.id == person_id)).one()
            print(f"name person id={person.id} -> name")
            person.name = name
            session.commit()

    print(f"redirecting to {redirect_to}")
    return redirect(redirect_to)
