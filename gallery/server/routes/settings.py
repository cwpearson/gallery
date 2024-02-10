from pathlib import Path

from sanic.response import html
from sanic.request import Request
from sanic import Blueprint

from jinja2 import Environment, FileSystemLoader, select_autoescape

from gallery import model, config

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"

env = Environment(
    loader=FileSystemLoader(TEMPLATES_DIR), autoescape=select_autoescape()
)


bp = Blueprint("settings")


@bp.get("/settings")
def bp_settings(request: Request):
    print(f"at /settings")

    template = env.get_template("settings.html")

    originals_dir = None
    if config.ORIGINALS_DIR:
        originals_dir = config.ORIGINALS_DIR

    return html(
        template.render(
            cache_dir=config.CACHE_DIR,
            originals_dir=originals_dir,
        )
    )
