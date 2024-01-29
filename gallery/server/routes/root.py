from sanic.response import redirect
from sanic import Blueprint

bp = Blueprint("root")


@bp.route("/")
def bp_root(request):
    return redirect("/gallery?offset=0&limit=25")
