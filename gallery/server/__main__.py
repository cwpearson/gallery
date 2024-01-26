from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
import sqlite3
import re

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
    pass


ROUTES = {
    "/person/[0-9]+": handle_person,
    "/people": handle_people,
    "/": handle_root,
}


class MyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        for pattern in ROUTES.keys():
            if re.match(pattern, self.path):
                print("matched", pattern)
                self.send_response(200)
                self.send_header("Content-type", "text/html")
                self.end_headers()
                ROUTES[pattern](self)
                return

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
