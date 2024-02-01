from sanic.response import redirect
from sanic.request import Request
from sanic import Blueprint

from sqlalchemy.orm import Session
from sqlalchemy import select

from whoosh.index import open_dir

from gallery import model
from gallery.model import Face


bp = Blueprint("hide-face")


@bp.post("/api/v1/hide-face")
def bp_image(request: Request):
    print(f"at /api/v1/hide-face")

    face_id = int(request.form.get("face_id"))

    with Session(model.get_engine()) as session:
        face = session.scalars(select(Face).where(Face.id == face_id)).one()
        face.hidden = True
        face.hidden_reason = model.HIDDEN_REASON_MANUAL
        session.commit()

    model.update_labels()

    redirect_to = request.headers.get("referer")
    print(f"redirecting to {redirect_to}")
    return redirect(redirect_to)
