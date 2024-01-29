from pathlib import Path
import os

from sanic.response import html
from sanic.request import Request
from sanic import Blueprint

from jinja2 import Environment, FileSystemLoader, select_autoescape

from sqlalchemy.orm import Session
from sqlalchemy import select, desc

from gallery import model
from gallery import cli_add_original

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"

env = Environment(
    loader=FileSystemLoader(TEMPLATES_DIR), autoescape=select_autoescape()
)


bp = Blueprint("gallery")


@bp.get("/gallery")
def bp_gallery(request: Request):
    print("at /gallery")

    # retrieve limit and offset
    limit = int(request.args.get("limit"))
    offset = int(request.args.get("offset"))
    print(f"limit={limit} offset={offset}")

    with Session(model.get_engine()) as session:
        images = session.scalars(
            select(model.Image)
            .order_by(desc(model.Image.created_at))
            .offset(offset)
            .limit(limit)
        ).all()

    next_offset = offset + limit
    prev_offset = max(0, offset - limit)
    next_limit = limit
    prev_limit = limit

    template = env.get_template("gallery.html")
    return html(
        template.render(
            images=images,
            next_offset=next_offset,
            prev_offset=prev_offset,
            next_limit=next_limit,
            prev_limit=prev_limit,
        ),
    )
