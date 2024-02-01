from sanic.response import redirect
from sanic.request import Request
from sanic import Blueprint

from sqlalchemy.orm import Session
from sqlalchemy import select

from gallery import model
from gallery.model import Person


bp = Blueprint("delete-person")


@bp.post("/api/v1/delete-person")
def bp_person(request: Request):
    """
    Delete a person.

    * Do not delete any images
    * Update Faces.person_id to NULL: this should happen automatically due to sqlalchemy back_populates
    """

    print(f"at /api/v1/delete-person")

    person_id = int(request.form.get("id"))
    redirect_to = request.form.get("redirect_to")

    with Session(model.get_engine()) as session:
        person = session.scalars(
            select(Person).where(Person.id == person_id)
        ).one_or_none()
        if person:
            print(f"delete person id={person.id}")
            session.delete(person)
            session.commit()

    print(f"redirecting to {redirect_to}")
    return redirect(redirect_to)
