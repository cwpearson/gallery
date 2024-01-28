from http.server import HTTPServer, BaseHTTPRequestHandler, SimpleHTTPRequestHandler
from pathlib import Path
import sqlite3
import re
import os
import urllib
from tempfile import TemporaryDirectory

from jinja2 import Environment, FileSystemLoader, select_autoescape
from requests_toolbelt.multipart import decoder
import requests_toolbelt

from sqlalchemy.orm import Session
from sqlalchemy import select

from gallery import model
from gallery import cli_add_original

# https://medium.com/@andrewklatzke/creating-a-python3-webserver-from-the-ground-up-4ff8933ecb96

TEMPLATES_DIR = Path(__file__).parent / "templates"

env = Environment(
    loader=FileSystemLoader(TEMPLATES_DIR), autoescape=select_autoescape()
)


def handle_root(h: BaseHTTPRequestHandler):
    print("handle_root")

    h.send_response(302)
    h.send_header("Location", "/view?offset=0&limit=25")
    h.end_headers()


def handle_view(h: BaseHTTPRequestHandler):
    print("handle_view")

    h.send_response(200)
    h.send_header("Content-type", "text/html")
    h.end_headers()

    # retrieve limit and offset
    components = urllib.parse.urlparse(h.path)
    result = urllib.parse.parse_qs(components.query)
    print(result)
    limit = result.get("limit", [25])[0]
    offset = result.get("offset", [0])[0]

    with Session(model.get_engine()) as session:
        images = session.scalars(
            select(model.Image)
            .order_by(model.Image.created_at)
            .offset(offset)
            .limit(limit)
        ).all()

    image_prefix = model.ORIGINALS_DIR.resolve().relative_to(os.getcwd())

    template = env.get_template("gallery.html")

    next_offset = offset + limit
    prev_offset = offset - limit
    next_limit = limit
    prev_limit = limit

    h.wfile.write(
        bytes(
            template.render(
                image_prefix=image_prefix,
                images=images,
                next_offset=next_offset,
                prev_offset=prev_offset,
                next_limit=next_limit,
                prev_limit=prev_limit,
            ),
            "utf-8",
        )
    )


def handle_people(handler: BaseHTTPRequestHandler):
    print("handle_people")

    handler.send_response(200)
    handler.send_header("Content-type", "text/html")
    handler.end_headers()

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


def handle_get_upload(handler: BaseHTTPRequestHandler):
    print("handle_get_upload")

    handler.send_response(200)
    handler.send_header("Content-type", "text/html")
    handler.end_headers()

    template = env.get_template("upload.html")

    conn = sqlite3.connect(model.DB_PATH)

    handler.wfile.write(
        bytes(
            template.render(),
            "utf-8",
        )
    )

    conn.close()


def handle_get_person(handler: BaseHTTPRequestHandler):
    handler.send_response(200)
    handler.send_header("Content-type", "text/html")
    handler.end_headers()

    person_id = int(handler.path[handler.path.rfind("/") + 1 :])
    print(f"handle_get_person: person_id={person_id}")

    conn = sqlite3.connect(model.DB_PATH)
    person_name = model.get_person_name(conn, person_id)

    originals = model.get_originals_for_person(conn, person_id)

    images = []
    for o in originals:
        image_id = o[0]

        # get faces from this image that are of this person
        faces = model.get_faces_for_original(conn, image_id)
        image_faces = []
        for f in faces:
            face_id = f[0]
            face_person_id = f[9]
            if face_person_id != person_id:
                continue
            image_faces += [
                {
                    "src": (model.FACES_DIR / f[8]).resolve().relative_to(os.getcwd()),
                    "id": face_id,
                }
            ]

        print(image_faces)
        images += [
            {
                "src": (model.ORIGINALS_DIR / o[1]).resolve().relative_to(os.getcwd()),
                "id": image_id,
                "faces": image_faces,
            }
        ]

    name_suggestions = [p[1] for p in model.get_people(conn)]

    template = env.get_template("person.html")

    handler.wfile.write(
        bytes(
            template.render(
                person_name=person_name,
                person_id=person_id,
                images=images,
                name_suggestions=name_suggestions,
            ),
            "utf-8",
        )
    )


def handle_image(handler: BaseHTTPRequestHandler):
    handler.send_response(200)
    handler.send_header("Content-type", "text/html")
    handler.end_headers()

    image_id = handler.path[handler.path.rfind("/") + 1 :]
    print(f"handle_image: image_id={image_id}")

    conn = sqlite3.connect(model.DB_PATH)
    original = model.get_original(conn, image_id)

    file_path = original[1]
    original_name = original[2]
    height = original[3]
    width = original[4]
    img_hash = original[5]
    file_hash = original[6]

    img_path = (model.ORIGINALS_DIR / file_path).resolve().relative_to(os.getcwd())

    all_faces = model.get_faces_for_original(conn, image_id, include_hidden=True)

    faces = [
        (Path(model.FACES_DIR / f[8]).resolve().relative_to(os.getcwd()), f[9], f[0])
        for f in all_faces
    ]
    # Look up labeled faces

    # Looks up auto-labeled faces

    # Look up hidden faces

    template = env.get_template("image.html")

    handler.wfile.write(
        bytes(
            template.render(
                image_id=image_id,
                img_path=img_path,
                original_name=original_name,
                height=height,
                width=width,
                img_hash=img_hash,
                file_hash=file_hash,
                faces=faces,
            ),
            "utf-8",
        )
    )


def handle_label(handler: BaseHTTPRequestHandler):
    handler.send_response(200)
    handler.send_header("Content-type", "text/html")
    handler.end_headers()

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
        img_path = (
            (model.ORIGINALS_DIR / original[1]).resolve().relative_to(Path(os.getcwd()))
        )
        original_name = original[2]
        face_path = (model.FACES_DIR / face[8]).resolve().relative_to(Path(os.getcwd()))
        records += [(face_id, str(face_path), str(img_path), original_name)]

    print(f"handle_label: {len(records)} records")

    people = model.get_people(conn)

    name_suggestions = [p[1] for p in people]
    handler.wfile.write(
        bytes(
            template.render(
                records=records,
                name_suggestions=name_suggestions,
            ),
            "utf-8",
        )
    )


class Re:
    def __init__(self, val):
        self.val = val


GET_ROUTES = {
    Re("/person/[0-9]+"): handle_get_person,
    Re("/image/[0-9]+"): handle_image,
    Re("/view*"): handle_view,
    "/upload": handle_get_upload,
    "/people": handle_people,
    "/label": handle_label,
    "/": handle_root,
}


def handle_post_label_many(h: BaseHTTPRequestHandler):
    conn = sqlite3.Connection(model.DB_PATH)
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
            person_id = model.get_person_by_name_exact(v)
            if person_id is None:
                person_id = model.new_person(v)
            model.set_face_person(
                face_id=face_id,
                person_id=person_id,
                person_source=model.PERSON_SOURCE_MANUAL,
            )
        if field == "hidden" and v == "on":
            model.set_face_hidden(
                face_id=face_id,
                hidden=True,
                hidden_reason=model.HIDDEN_REASON_MANUAL,
            )

    cli_add_original.update_labels()

    # redirect back where we sumbitted the post from
    h.send_response(302)
    h.send_header("Location", h.headers["Referer"])
    h.end_headers()

    conn.close()
    return


def handle_post_label_one(h: BaseHTTPRequestHandler):
    conn = sqlite3.Connection(model.DB_PATH)
    content_length = int(h.headers["Content-Length"])
    raw_data = h.rfile.read(content_length).decode("utf-8")
    data = urllib.parse.parse_qs(raw_data)

    face_id = data["face_id"][0]
    name = data["name"][0]
    if name:
        person_id = model.get_person_by_name_exact(name)
        if person_id is None:
            person_id = model.new_person(name)
        model.set_face_person(conn, face_id, person_id, model.PERSON_SOURCE_MANUAL)
        cli_add_original.update_labels()

    # redirect back where we sumbitted the post from
    h.send_response(302)
    h.send_header("Location", h.headers["Referer"])
    h.end_headers()

    conn.close()
    return


def handle_post_upload_files(h: BaseHTTPRequestHandler):
    content_type_enc = "Content-Type".encode("utf-8")
    image_enc = "image/".encode("utf-8")

    # print(h.headers)
    conn = sqlite3.Connection(model.DB_PATH)
    content_length = int(h.headers["Content-Length"])
    post_data = h.rfile.read(content_length)

    data = decoder.MultipartDecoder(post_data, h.headers["Content-Type"])
    for part in data.parts:
        if content_type_enc in part.headers:
            if image_enc in part.headers[content_type_enc]:
                disp = part.headers["Content-Disposition".encode("utf-8")].decode(
                    "utf-8"
                )
                print(disp)
                match = re.search('filename="(.*)"\s*;?', disp)
                uploaded_name = match[1]
                print(uploaded_name)

                with TemporaryDirectory(dir=os.getcwd()) as d:
                    uploaded_path = Path(d) / uploaded_name
                    with open(uploaded_path, "wb") as f:
                        f.write(part.content)
                    cli_add_original.add_original(uploaded_path)
        # for key, value in part.headers.items():
        #     print(key, value)
        # if b"filename=" in part.headers.values():
        #     print(part.content)  # Alternatively, part.text if you want unicode

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
                print(self.path, "matched Re", key.val)
                GET_ROUTES[key](self)
                return
            elif isinstance(key, str) and key == self.path:
                print("exact", key)
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
        elif self.path == "/api/v1/upload-files":
            handle_post_upload_files(self)
        elif self.path == "/api/v1/label-one":
            handle_post_label_one(self)


def run(server_class=HTTPServer, handler_class=MyHandler):
    server_address = ("", 8000)
    httpd = server_class(server_address, handler_class)
    httpd.serve_forever()


if __name__ == "__main__":
    run()
