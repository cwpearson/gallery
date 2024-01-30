from pathlib import Path
import os
from tempfile import TemporaryDirectory

from sanic.response import html, redirect
from sanic.request import Request
from sanic import Blueprint

from jinja2 import Environment, FileSystemLoader, select_autoescape

from sqlalchemy.orm import Session
from sqlalchemy import select

from gallery import model
from gallery import cli_add_original

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"

env = Environment(
    loader=FileSystemLoader(TEMPLATES_DIR), autoescape=select_autoescape()
)


bp = Blueprint("upload")


@bp.get("/upload")
def bp_upload(request: Request):
    print("at /upload")

    template = env.get_template("upload.html")
    return html(
        template.render(),
    )


@bp.post("/api/v1/upload-files")
def bp_upload_files(request: Request):
    print("at /api/v1/upload-files")

    for key in request.files.keys():
        files = request.files.getlist(key)
        for file in files:
            with TemporaryDirectory(dir=os.getcwd()) as d:
                uploaded_path = Path(d) / file.name
                with open(uploaded_path, "wb") as f:
                    f.write(file.body)
                cli_add_original.add_original(uploaded_path)

    model.incremental_index()
    model.detect_faces()
    model.generate_embeddings()
    model.update_labels()

    return redirect(request.headers.get("Referer"))
