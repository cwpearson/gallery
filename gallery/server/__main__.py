from http.server import HTTPServer, BaseHTTPRequestHandler, SimpleHTTPRequestHandler
from pathlib import Path
import sqlite3
import re
import os

from jinja2 import Environment, FileSystemLoader, select_autoescape

from gallery import model

# https://medium.com/@andrewklatzke/creating-a-python3-webserver-from-the-ground-up-4ff8933ecb96

TEMPLATES_DIR = Path(__file__).parent / "templates"

env = Environment(
    loader=FileSystemLoader(TEMPLATES_DIR), autoescape=select_autoescape()
)


def handle_root(handler):
    pass


def handle_people(handler: BaseHTTPRequestHandler):
    print("handle_people")
    template = env.get_template("people.html")

    conn = sqlite3.connect(model.DB_PATH)
    people = model.get_people(conn)

    handler.wfile.write(
        bytes(
            template.render(
                navigation=[
                    {"href": "/", "caption": "home"},
                    {"href": "/people", "caption": "people"},
                ],
                people=people,
            ),
            "utf-8",
        )
    )


def handle_person(handler: BaseHTTPRequestHandler):
    person_id = handler.path[handler.path.rfind("/") + 1 :]
    print(f"handle_person: person_id={person_id}")

    conn = sqlite3.connect(model.DB_PATH)
    originals = model.get_originals_for_person(conn, person_id)

    img_paths = [
        (model.ORIGINALS_DIR / o[1]).resolve().relative_to(os.getcwd())
        for o in originals
    ]

    template = env.get_template("person.html")

    handler.wfile.write(
        bytes(
            template.render(
                img_paths=img_paths,
            ),
            "utf-8",
        )
    )


def handle_label(handler: BaseHTTPRequestHandler):
    template = env.get_template("label.html")
    conn = sqlite3.connect(model.DB_PATH)

    # retrieve all unlabeled faces
    faces = model.get_faces_for_person(conn, person_id=None)

    # for each unlabeled face, retrieve image
    records = []
    for face in faces:
        face_id = face[0]
        original_id = face[1]
        original = model.get_original(conn, original_id)
        original_path = (
            (model.ORIGINALS_DIR / original[1]).resolve().relative_to(Path(os.getcwd()))
        )
        face_path = (model.FACES_DIR / face[8]).resolve().relative_to(Path(os.getcwd()))
        records += [(face_id, str(face_path), str(original_path))]

    print(f"handle_label: {len(records)} records")

    handler.wfile.write(
        bytes(
            template.render(records=records),
            "utf-8",
        )
    )


class Re:
    def __init__(self, val):
        self.val = val


ROUTES = {
    Re("/person/[0-9]+"): handle_person,
    "/people": handle_people,
    "/label": handle_label,
    "/": handle_root,
}


class MyHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        for key in ROUTES.keys():
            if isinstance(key, Re) and re.match(key.val, self.path):
                print("Re", key.val)
                self.send_response(200)
                self.send_header("Content-type", "text/html")
                self.end_headers()
                ROUTES[key](self)
                return
            elif isinstance(key, str) and key == self.path:
                print("exact", key)
                self.send_response(200)
                self.send_header("Content-type", "text/html")
                self.end_headers()
                ROUTES[key](self)
                return

        # fallback to whatever the simple one does
        return SimpleHTTPRequestHandler.do_GET(self)

        self.send_response(404)
        # self.send_header("Content-type", "text/html")
        self.end_headers()
        # self.wfile.write(
        #     bytes("<html><head><title>https://pythonbasics.org</title></head>", "utf-8")
        # )
        # self.wfile.write(bytes("<p>Request: %s</p>" % self.path, "utf-8"))
        # self.wfile.write(bytes("<body>", "utf-8"))
        # self.wfile.write(bytes("<p>This is an example web server.</p>", "utf-8"))
        # self.wfile.write(bytes("</body></html>", "utf-8"))


def run(server_class=HTTPServer, handler_class=MyHandler):
    server_address = ("", 8000)
    httpd = server_class(server_address, handler_class)
    httpd.serve_forever()


if __name__ == "__main__":
    run()
