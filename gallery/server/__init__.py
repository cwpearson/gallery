from pathlib import Path

from sanic import Sanic
from sanic.response import html, text


from gallery.server.routes import (
    root,
    delete_image,
    gallery,
    image,
    label_one,
    label_many,
    label,
    people,
    person,
    search,
    upload,
)
from gallery import model


model.init()

app = Sanic("Gallery")
app.static("/static/css/", Path(__file__).parent / "css", name="css")
app.static("/static/image/", model.ORIGINALS_DIR, name="images")
app.static("/static/face/", model.FACES_DIR, name="faces")
app.blueprint(root.bp)
app.blueprint(gallery.bp)
app.blueprint(upload.bp)
app.blueprint(label_one.bp)
app.blueprint(label_many.bp)
app.blueprint(label.bp)
app.blueprint(people.bp)
app.blueprint(person.bp)
app.blueprint(image.bp)
app.blueprint(search.bp_get)
app.blueprint(search.bp_post)
app.blueprint(delete_image.bp)
