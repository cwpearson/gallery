from pathlib import Path

from sanic.response import html, redirect
from sanic.request import Request
from sanic import Blueprint

from jinja2 import Environment, FileSystemLoader, select_autoescape

from sqlalchemy.orm import Session
from sqlalchemy import select

from whoosh.index import open_dir
from whoosh.qparser import QueryParser

from gallery import model
from gallery.model import Face, Image, Person


TEMPLATES_DIR = Path(__file__).parent.parent / "templates"

env = Environment(
    loader=FileSystemLoader(TEMPLATES_DIR), autoescape=select_autoescape()
)


bp_get = Blueprint("search")


@bp_get.get("/search")
def bp_search(request: Request):
    print("at /search")

    template = env.get_template("search.html")
    return html(template.render())


bp_post = Blueprint("api-v1-search")


@bp_post.post("/api/v1/search")
def bp_search(request: Request):
    print("at /api/v1/search")

    query_str = request.form.get("query")
    print(query_str)

    ix = open_dir(model.WHOOSH_DIR, readonly=True)
    qp = QueryParser("comment", schema=ix.schema)
    q = qp.parse(query_str)

    with ix.searcher() as s:
        results = s.search(q)
        result_ids = [int(r["id"]) for r in results]

    images = []
    with Session(model.get_engine()) as session:
        for image_id in result_ids:
            image = session.scalars(select(Image).where(Image.id == image_id)).one()
            images += [image]

    template = env.get_template("results.html")
    return html(
        template.render(
            query=query_str,
            images=images,
        )
    )
