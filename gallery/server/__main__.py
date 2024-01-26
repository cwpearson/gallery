from http.server import HTTPServer, BaseHTTPRequestHandler, SimpleHTTPRequestHandler
from pathlib import Path
import sqlite3
import re
import os
import urllib

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


GET_ROUTES = {
    Re("/person/[0-9]+"): handle_person,
    "/people": handle_people,
    "/label": handle_label,
    "/": handle_root,
}


def handle_post_label_many(h: BaseHTTPRequestHandler):
    conn = sqlite3.Connection(model.DB_PATH)
    print(f"do_POST: h.path={h.path}")
    content_length = int(h.headers["Content-Length"])
    post_data = h.rfile.read(content_length).decode("utf-8")

    post_kvs = urllib.parse.parse_qs(post_data)
    # print(post_kvs)

    for k, vs in post_kvs.items():
        v = vs[0]  # unique name for each value
        sep = k.find("-")
        face_id = int(k[:sep])
        field = k[sep + 1 :]
        print(face_id, field, v)

        if field == "name" and v:
            person_id = model.get_person_by_name_exact(conn, v)
            if person_id is None:
                person_id = model.new_person(conn, v)
            model.set_face_person(
                conn,
                face_id=face_id,
                person_id=person_id,
                person_source=model.PERSON_SOURCE_MANUAL,
            )
        if field == "hidden" and v == "on":
            model.set_face_hidden(
                conn,
                face_id=face_id,
                hidden=True,
                hidden_reason=model.HIDDEN_REASON_MANUAL,
            )

    # redirect back where we sumbitted the post from
    h.send_response(302)
    h.send_header("Location", h.headers["Referer"])
    h.end_headers()

    conn.close()
    return


class MyHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        for key in GET_ROUTES.keys():
            if isinstance(key, Re) and re.match(key.val, self.path):
                print("Re", key.val)
                self.send_response(200)
                self.send_header("Content-type", "text/html")
                self.end_headers()
                GET_ROUTES[key](self)
                return
            elif isinstance(key, str) and key == self.path:
                print("exact", key)
                self.send_response(200)
                self.send_header("Content-type", "text/html")
                self.end_headers()
                GET_ROUTES[key](self)
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

    def do_POST(self):
        # print(self.headers)
        print(f"do_POST: self.path={self.path}")
        if self.path == "/api/v1/label-many":
            handle_post_label_many(self)


def run(server_class=HTTPServer, handler_class=MyHandler):
    server_address = ("", 8000)
    httpd = server_class(server_address, handler_class)
    httpd.serve_forever()


if __name__ == "__main__":
    run()
