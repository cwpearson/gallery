from pathlib import Path
import multiprocessing
import sqlite3
import json
from typing import Tuple
import datetime
import shutil

from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy import Text, Integer, DateTime
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy import select

import face_recognition
import numpy as np
from sklearn.cluster import DBSCAN
import numpy as np
from PIL import Image as PilImage

from gallery import utils

from whoosh.index import create_in, open_dir
import whoosh.fields
from whoosh.writing import AsyncWriter
import whoosh

PERSON_SOURCE_MANUAL = 1
PERSON_SOURCE_AUTOMATIC = 2

HIDDEN_REASON_SMALL = 1
HIDDEN_REASON_MANUAL = 2

CPUS = max(multiprocessing.cpu_count() - 1, 1)

CACHE_DIR = Path(__file__).parent / ".." / ".gallery"

ORIGINALS_DIR = CACHE_DIR / "originals"
FACES_DIR = CACHE_DIR / "faces"
DB_PATH = CACHE_DIR / "gallery.db"
WHOOSH_DIR = CACHE_DIR / "whoosh"

WHOOSH_SCHEMA = whoosh.fields.Schema(
    id=whoosh.fields.ID(stored=True),
    comment=whoosh.fields.TEXT,
)


class Base(DeclarativeBase):
    pass


class Image(Base):
    __tablename__ = "images"
    id: Mapped[int] = mapped_column(primary_key=True)
    file_name: Mapped[str] = mapped_column(Text)
    original_name: Mapped[str] = mapped_column(Text)
    height: Mapped[int] = mapped_column(Integer)
    width: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow
    )  # time in UTC
    image_hash: Mapped[str] = mapped_column(Text)  # hash of the image data
    file_hash: Mapped[str] = mapped_column(Text)  # hash of the file data
    comment: Mapped[str] = mapped_column(Text, default="")


class Face(Base):
    __tablename__ = "faces"
    id: Mapped[int] = mapped_column(primary_key=True)
    image_id: Mapped[int] = mapped_column(Integer)
    top: Mapped[int] = mapped_column(Integer)
    right: Mapped[int] = mapped_column(Integer)
    bottom: Mapped[int] = mapped_column(Integer)
    left: Mapped[int] = mapped_column(Integer)
    hidden: Mapped[int] = mapped_column(Integer)
    hidden_reason: Mapped[int] = mapped_column(Integer, nullable=True)
    extracted_path: Mapped[str] = mapped_column(Text)
    person_id: Mapped[int] = mapped_column(Integer, nullable=True)
    person_source: Mapped[int] = mapped_column(Integer, nullable=True)
    excluded_people: Mapped[str] = mapped_column(Text)
    embedding_json: Mapped[str] = mapped_column(Text, nullable=True)


class Person(Base):
    __tablename__ = "people"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(Text)


ENGINE = None


def get_engine():
    global ENGINE
    if ENGINE is None:
        DB_PATH.parent.mkdir(exist_ok=True, parents=True)
        engine_path = f"sqlite:///{DB_PATH.resolve()}"
        print(f"open {engine_path}")
        ENGINE = create_engine(engine_path, echo=False)
    return ENGINE


def init():
    # sqlite database
    engine = get_engine()
    Base.metadata.create_all(engine)

    # whoosh database
    WHOOSH_DIR.mkdir(exist_ok=True, parents=True)
    if not whoosh.index.exists_in(WHOOSH_DIR):
        print(f"creating whoosh index in {WHOOSH_DIR}")
        create_in(WHOOSH_DIR, WHOOSH_SCHEMA)


def new_person(name: str) -> int:
    with Session(get_engine()) as session:
        person = Person(name=name)
        session.add(person)
        session.commit()
        return person.id


def all_embeddings(include_hidden=False) -> list:
    with Session(get_engine()) as session:
        query = select(Face).where(Face.embedding_json != None)
        if not include_hidden:
            query = query.where(Face.hidden == 0)
        faces = session.scalars(query).all()

        return [json.loads(face.embedding_json) for face in faces], [
            face.id for face in faces
        ]


def get_face_person(face_id: int):
    """
    return person_id, person_source for face_id
    """
    # print(f"get_face_person({face_id})")

    with Session(get_engine()) as session:
        face = session.scalars(select(Face).where(Face.id == face_id)).one()
        return face.person_id, face.person_source


def set_face_person(face_id: int, person_id: int, person_source: int):
    print(f"set face {face_id} to person {person_id}")
    with Session(get_engine()) as session:
        face = session.scalars(select(Face).where(Face.id == face_id)).one()

        face.person_id = person_id
        face.person_source = person_source
        session.commit()


def get_person_name(conn: sqlite3.Connection, person_id: int) -> Tuple[str, None]:
    """return name for person_id"""

    cursor = conn.cursor()
    face_row = cursor.execute(
        "SELECT name FROM people WHERE id = ?", (person_id,)
    ).fetchone()
    cursor.close()

    if face_row:
        return face_row[0]
    else:
        return None


def face_add_excluded_person(conn: sqlite3.Connection, face_id: int, person_id: int):
    cursor = conn.cursor()
    face_row = cursor.execute(
        "SELECT id, excluded_people FROM faces WHERE id = ?",
        (face_id,),
    ).fetchone()

    _, excluded_people_str = face_row

    if excluded_people_str:
        excluded_people = json.loads(excluded_people_str)
    else:
        excluded_people = []
    excluded_people += [person_id]
    excluded_people = list(set(excluded_people))  # uniqify
    print(excluded_people)

    face_row = cursor.execute(
        "UPDATE faces SET excluded_people = ? WHERE id = ?",
        (json.dumps(excluded_people), face_id),
    )
    conn.commit()
    cursor.close()


def get_person_by_name_exact(name: str) -> int:
    "get the id of the person whose name matches exactly. None if no such person"

    with Session(get_engine()) as session:
        person = session.scalars(select(Person).where(Person.name == name)).one()
        if person is None:
            return None
        else:
            return person.id


def get_people_by_name_near(conn: sqlite3.Connection, name: str):
    cursor = conn.cursor()
    fields = name.split(" ")
    fields = [x for f in fields for x in f.split("-")]

    query = (
        "SELECT id, name FROM people WHERE (name != ?) AND ("
        + " OR ".join("name LIKE ?" for _ in fields)
        + ")"
    )

    people_rows = cursor.execute(
        query, (name,) + tuple(f"%{f}%" for f in fields)
    ).fetchall()

    return [id for id, _ in people_rows], [name for _, name in people_rows]


def get_people(conn: sqlite3.Connection) -> list:
    cursor = conn.cursor()
    rows = cursor.execute("SELECT * FROM people").fetchall()
    cursor.close()
    return rows


def get_faces_for_person(conn: sqlite3.Connection, person_id: int) -> list:
    cursor = conn.cursor()
    if person_id is None:
        rows = cursor.execute(
            "SELECT * FROM faces WHERE person_id IS NULL AND hidden = 0"
        ).fetchall()
    else:
        rows = cursor.execute(
            "SELECT * FROM faces WHERE person_id = ? AND hidden = 0", (person_id,)
        ).fetchall()
    cursor.close()
    return rows


def get_original(conn: sqlite3.Connection, image_id: int) -> list:
    cursor = conn.cursor()
    row = cursor.execute("SELECT * FROM images WHERE id = ?", (image_id,)).fetchone()
    cursor.close()
    return row


def get_originals_for_person(conn: sqlite3.Connection, person_id: int) -> list:
    faces = get_faces_for_person(conn, person_id)

    image_ids = set()

    for face in faces:
        image_id = face[1]
        image_ids.add(image_id)

    originals = []
    for image_id in image_ids:
        originals += [get_original(conn, image_id)]

    return originals


def set_face_hidden(face_id, hidden: bool, hidden_reason: int):
    print(f"set face {face_id} hidden={hidden} hidden_reason={hidden_reason}")
    with Session(get_engine()) as session:
        face = session.scalars(select(Face).where(Face.id == face_id)).one()
        face.hidden = hidden
        face.hidden_reason = hidden_reason
        session.commit()


def get_faces_for_original(
    conn: sqlite3.Connection, image_id: int, include_hidden=False
) -> list:
    cursor = conn.cursor()

    query = "SELECT * FROM faces WHERE image_id = ?"
    if not include_hidden:
        query += " AND hidden = 0"

    rows = cursor.execute(query, (image_id,)).fetchall()
    cursor.close()
    return rows


def detect_face(image_id):
    with Session(get_engine()) as session:
        image = session.get(Image, image_id)
        faces = session.scalars(select(Face).where(Face.image_id == image_id)).all()

        if not faces:
            image_path = ORIGINALS_DIR / image.file_name
            fr_image = face_recognition.load_image_file(image_path)
            locations = face_recognition.face_locations(fr_image)
            for y1, x2, y2, x1 in locations:  # [(t, r, b, l)]
                face_height = y2 - y1
                face_width = x2 - x1

                print(f"image {image_id} : found face at {(x1, y1, x2, y2)}")
                face_is_small = (
                    face_height / image.height < 0.04 or face_width / image.width < 0.04
                )
                hidden = False
                hidden_reason = None
                if face_is_small:
                    print(
                        f"image {image_id}: face at {(x1, y1, x2, y2)} will be hidden (too small)"
                    )
                    hidden = True
                    hidden_reason = HIDDEN_REASON_SMALL

                pil_image = PilImage.open(image_path)
                cropped = pil_image.crop((x1, y1, x2, y2))
                cropped_sha = utils.hash_image_data(cropped)
                output_name = Path(f"{cropped_sha[0:2]}") / f"{cropped_sha[0:8]}.png"
                output_path = CACHE_DIR / "faces" / output_name
                output_path.parent.mkdir(exist_ok=True, parents=True)
                print(output_path)
                cropped.save(output_path)

                session.add(
                    Face(
                        image_id=image_id,
                        top=y1,
                        right=x2,
                        bottom=y2,
                        left=x1,
                        hidden=hidden,
                        hidden_reason=hidden_reason,
                        extracted_path=str(output_name),
                        excluded_people=json.dumps([]),
                    )
                )
            session.commit()

        else:
            print(f"already detected faces for {image_id}")


def detect_faces():
    init()

    with Session(get_engine()) as session:
        images = session.scalars(select(Image))

        for image in images:
            detect_face(image.id)

        # with multiprocessing.Pool(CPUS) as p:
        #     p.starmap(detect_face, [(image.id,) for image in images])


def generate_embeddings():
    init()

    with Session(get_engine()) as session:
        faces = session.scalars(
            select(Face).where(Face.embedding_json == None).where(Face.hidden == 0)
        ).all()

        for face in faces:
            # retrieve image for face
            image = session.scalars(
                select(Image).where(Image.id == face.image_id)
            ).one()

            original_img = face_recognition.load_image_file(
                ORIGINALS_DIR / image.file_name
            )
            encoding = face_recognition.face_encodings(
                original_img,
                known_face_locations=[(face.top, face.right, face.bottom, face.left)],
            )[0]
            # print(encoding)

            data_str = json.dumps(encoding.tolist())

            print(f"face {face.id}: update embedding {data_str[:20]}...")
            face.embedding_json = data_str
            session.commit()


def update_labels():
    """
    Cluster all the embeddings with DBSCAN
    This will produce a variety of clusters
    Each face in the cluster may be labeled
        - If so, assign each face in the cluster to the closest manually-labeled face in that cluster
        - Otherwise, create a new anonymous person and assign all faces in the cluster to that person
    """

    init()

    embeddings, face_ids = all_embeddings()
    print(f"clustering {len(embeddings)} faces...")

    X = np.array(embeddings)

    clustering = DBSCAN(eps=0.44, min_samples=3, metric="euclidean").fit(X)
    # print(clustering.labels_)

    clusters = {}
    for xi, cluster_id in enumerate(clustering.labels_):
        clusters[cluster_id] = clusters.get(cluster_id, []) + [xi]

    print(f"processing {len(clusters)} clusters...")

    for cluster_id, xis in clusters.items():
        if cluster_id == -1:
            continue

        # print(f"processing cluster {cluster_id}")

        cluster_labeled_faces = []
        for xi in xis:
            label, reason = get_face_person(face_ids[xi])
            if reason == PERSON_SOURCE_MANUAL:
                cluster_labeled_faces += [(xi, label, reason)]

        # print(cluster_labeled_faces)

        # label each unlabeled face in the cluster to the closest labeled face in the cluster
        if cluster_labeled_faces:
            for xi in xis:
                _, reason = get_face_person(face_ids[xi])
                if reason != PERSON_SOURCE_MANUAL:
                    min_dist_label = None
                    min_dist = 100000000  # big number
                    for labeled_xi, label, _ in cluster_labeled_faces:
                        if labeled_xi != xi:
                            dist = face_recognition.face_distance(
                                [np.array(embeddings[labeled_xi])],
                                np.array(embeddings[xi]),
                            )[0]
                            # print(f"dist with {xi} is {dist}")
                            if dist < min_dist and dist < 0.5:
                                min_dist_label = label
                                min_dist = dist

                    if min_dist_label:
                        current_person_id, _ = get_face_person(face_ids[xi])
                        if current_person_id != min_dist_label:
                            print(
                                f"updated unlabeled or auto-labeled xi={xi} to {min_dist_label}"
                            )
                            set_face_person(
                                face_ids[xi],
                                min_dist_label,
                                PERSON_SOURCE_AUTOMATIC,
                            )
                else:
                    pass  # this face in this cluster was already labeled
        else:
            # print(f"no labels faces in cluster {cluster_id}")
            pass


def add_original(image_path) -> int:
    image_path = Path(image_path)

    # check if the file is an exact duplicate of one we've seen before
    # this is faster than opening and rendering the image to compare the
    # data, so we can more quickly reject images we've seen before
    with open(image_path, "rb") as f:
        file_hash = utils.hash_file_data(f)

    with Session(get_engine()) as session:
        stmt = select(Image).where(Image.file_hash == file_hash)

        existing = session.scalars(stmt).one_or_none()
        if existing is not None:
            print(f"{image_path} file already present as image {existing.id}")
            return existing.id

    # check if the pixel values are identical to an image we already have
    # this is much slower than hashing the file data directly, but
    # prevents us from adding the same image twice just because the files are not the same
    with open(image_path, "rb") as file:
        pil_img = PilImage.open(file)
        img_hash = utils.hash_image_data(pil_img)

    whoosh_ix = open_dir(WHOOSH_DIR)
    whoosh_writer = AsyncWriter(whoosh_ix)

    with Session(get_engine()) as session:
        stmt = select(Image).where(Image.image_hash == img_hash)

        existing = session.scalars(stmt).one_or_none()
        if existing is not None:
            print(f"{image_path} image data already present as image {existing.id}")
            return existing.id
        else:
            # copy file to ORIGINALS_DIR
            dst_name = Path(f"{img_hash[0:2]}") / f"{img_hash[0:8]}{image_path.suffix}"
            dst_path = ORIGINALS_DIR / dst_name
            dst_path.parent.mkdir(exist_ok=True, parents=True)
            print(f"{image_path} -> {dst_path}")
            shutil.copyfile(image_path, dst_path)

            width, height = pil_img.size

            comment = pil_img.info["comment"]
            if isinstance(comment, bytes):
                comment = comment.decode("utf-8")

            img = Image(
                file_name=str(dst_name),
                original_name=image_path.name,
                height=height,
                width=width,
                image_hash=img_hash,
                file_hash=file_hash,
                comment=comment,
            )
            session.add(img)
            session.commit()

            whoosh_writer.add_document(
                id=str(img.id),
                comment=comment,
            )
            whoosh_writer.commit()

            return img.id
