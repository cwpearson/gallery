from pathlib import Path

from sanic.response import redirect
from sanic.request import Request
from sanic import Blueprint

from jinja2 import Environment, FileSystemLoader, select_autoescape

from sqlalchemy.orm import Session
from sqlalchemy import select

from gallery import model
from gallery import config


bp = Blueprint("rescan-originals")


async def rescan_originals_task(app, complete: bool = False):
    with Session(model.get_engine()) as session:

        IMAGE_SUFFIXES = [".jpg", ".png", ".webp", ".jpeg"]

        for e in config.ORIGINALS_DIR.rglob("*"):
            if e.is_file():
                if e.suffix in IMAGE_SUFFIXES:
                    model.add_original(e)


@bp.post("/api/v1/rescan-originals")
def rescan_originals(request: Request):

    print("at /api/v1/rescan-originals")

    # whether to do a complete rescan
    complete = request.form.get("complete")

    if not config.ORIGINALS_DIR:
        return redirect(request.headers.get("Referer"))

    model.log("starting async originals scan...")
    request.app.add_task(rescan_originals_task(request.app, complete))

    # redirect back where we sumbitted the post from
    referer = request.headers.get("Referer")
    print(f"redirect to referer {referer}")
    return redirect(referer)
