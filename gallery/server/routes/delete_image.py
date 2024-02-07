from sanic.response import redirect
from sanic.request import Request
from sanic import Blueprint

from sqlalchemy.orm import Session
from sqlalchemy import select

from whoosh.index import open_dir

from gallery import model
from gallery.model import Image


bp = Blueprint("delete-image")


@bp.post("/api/v1/delete-image")
def bp_image(request: Request):
    print(f"at /api/v1/delete-image")

    image_id = int(request.form.get("id"))
    redirect_to = request.form.get("redirect_to")

    files_to_remove = []

    with Session(model.get_engine()) as session:
        # delete the image
        print(f"delete Image {image_id}")
        image = session.scalars(select(Image).where(Image.id == image_id)).one()
        files_to_remove += [model.IMAGES_DIR / image.file_name]
        for face in image.faces:
            files_to_remove += [model.FACES_DIR / face.extracted_path]
        session.delete(image)
        session.commit()

        # delete the image file and face files
        for file in files_to_remove:
            print(f"delete {file}")
            file.unlink()

    # remove the image from the whoosh index
    ix = open_dir(model.WHOOSH_DIR)
    writer = ix.writer()
    print(f"delete whoosh document with id={image_id}")

    # this claims to return the number of documents deleted,
    # however, it seems to return 0 and yet the documents are
    # no longer returned by a search
    writer.delete_by_term("id", image_id)  # FIXME: does it work?
    writer.commit()

    print(f"redirecting to {redirect_to}")
    return redirect(redirect_to)
