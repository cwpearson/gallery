from pathlib import Path

from sanic.response import html, redirect
from sanic.request import Request
from sanic import Blueprint

from jinja2 import Environment, FileSystemLoader, select_autoescape

from sqlalchemy.orm import Session
from sqlalchemy import select, desc

from gallery import model
from gallery.model import Log

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"

env = Environment(
    loader=FileSystemLoader(TEMPLATES_DIR), autoescape=select_autoescape()
)


bp = Blueprint("logs")


@bp.get("/logs")
def bp_person(request: Request):
    model.log(f"at /logs")

    limit = int(request.args.get("limit", 1000))
    offset = int(request.args.get("offset", 0))
    model.log(f"limit={limit} offset={offset}")
    next_offset = offset + limit
    prev_offset = max(0, offset - limit)
    next_limit = limit
    prev_limit = limit

    template = env.get_template("logs.html")

    with Session(model.get_log_engine()) as session:
        logs = session.scalars(
            select(Log).order_by(desc(Log.unix)).limit(limit).offset(offset)
        ).all()

        return html(
            template.render(
                logs=logs,
                next_limit=next_limit,
                next_offset=next_offset,
                prev_limit=prev_limit,
                prev_offset=prev_offset,
            )
        )
