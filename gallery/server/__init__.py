from pathlib import Path

from sanic import Sanic


from gallery.server.routes import (
    root,
    delete_image,
    delete_person,
    gallery,
    hide_face,
    image,
    label_one,
    label_many,
    label,
    logs,
    name_person,
    new_people,
    people,
    person,
    search,
    upload,
)
from gallery import model
from gallery import config


model.init()

app = Sanic("Gallery", env_prefix="GALLERY_")

if hasattr(app.config, "ORIGINALS_DIR"):
    config.update(originals_dir=app.config.ORIGINALS_DIR)
if hasattr(app.config, "CACHE_DIR"):
    config.update(cache_dir=app.config.CACHE_DIR)

app.static("/static/css/", Path(__file__).parent / "css", name="css")
app.static("/static/image/", model.IMAGES_DIR, name="images")
app.static("/static/face/", model.FACES_DIR, name="faces")
app.blueprint(root.bp)
app.blueprint(gallery.bp)
app.blueprint(upload.bp)
app.blueprint(label_one.bp)
app.blueprint(label_many.bp)
app.blueprint(label.bp)
app.blueprint(logs.bp)
app.blueprint(name_person.bp)
app.blueprint(new_people.bp)
app.blueprint(people.bp)
app.blueprint(person.bp)
app.blueprint(image.bp)
app.blueprint(search.bp_get)
app.blueprint(search.bp_post)
app.blueprint(delete_image.bp)
app.blueprint(delete_person.bp)
app.blueprint(hide_face.bp)
