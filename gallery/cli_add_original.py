import sys
import multiprocessing

from sqlalchemy.orm import Session
from sqlalchemy import select

from gallery import model


if __name__ == "__main__":
    model.init()

    with multiprocessing.Pool(model.CPUS) as p:
        p.map(model.add_original, sys.argv[1:])

    model.incremental_index()

    with Session(model.get_engine()) as session:
        images = session.scalars(select(model.Image)).all()
        with multiprocessing.Pool(model.CPUS) as p:
            p.starmap(model.detect_face, [(image.id,) for image in images])

    model.generate_embeddings()

    model.update_labels()
