import multiprocessing

from sqlalchemy.orm import Session
from sqlalchemy import select

import click

from gallery import model
from gallery import config


@click.command()
@click.option("--cache-dir", help="Gallery cache directory")
@click.argument("paths", nargs=-1)
def add_images(paths, cache_dir: str = None):

    if cache_dir:
        config.update(cache_dir=cache_dir)

    model.init()

    with multiprocessing.Pool(model.CPUS) as p:
        p.map(model.add_original, paths)

    model.incremental_index()

    # try to detect faces in all images
    # add_original won't do it if the image has already been added
    with Session(model.get_engine()) as session:
        images = session.scalars(select(model.Image)).all()
        with multiprocessing.Pool(model.CPUS) as p:
            p.starmap(model.detect_face, [(image.id,) for image in images])

    model.generate_embeddings()

    model.update_labels()


if __name__ == "__main__":
    add_images()
