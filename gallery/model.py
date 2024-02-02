from pathlib import Path
import multiprocessing
import sqlite3
import json
from typing import Tuple
import datetime
import shutil
from typing import List
import time
import io


from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, Session
from sqlalchemy import Text, Integer, DateTime, ForeignKey, LargeBinary
from sqlalchemy import create_engine
from sqlalchemy import select

import face_recognition
import numpy as np
from sklearn.cluster import DBSCAN, HDBSCAN
from sklearn.neighbors import NearestNeighbors
import numpy as np
from PIL import Image as PilImage

from gallery import utils

from whoosh.index import create_in, open_dir
import whoosh.fields
from whoosh.writing import AsyncWriter
import whoosh
from whoosh.qparser import QueryParser

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
    id=whoosh.fields.NUMERIC(stored=True),
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
    title: Mapped[str] = mapped_column(Text, nullable=True)
    archived: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow
    )  # time in UTC
    image_hash: Mapped[str] = mapped_column(Text)  # hash of the image data
    file_hash: Mapped[str] = mapped_column(Text)  # hash of the file data
    comment: Mapped[str] = mapped_column(Text, default="")
    faces: Mapped[List["Face"]] = relationship(
        back_populates="image",  # Face.image
        cascade="all, delete-orphan",
    )


class Face(Base):
    __tablename__ = "faces"
    id: Mapped[int] = mapped_column(primary_key=True)
    image_id: Mapped[int] = mapped_column(ForeignKey("images.id"))
    top: Mapped[int] = mapped_column(Integer)
    right: Mapped[int] = mapped_column(Integer)
    bottom: Mapped[int] = mapped_column(Integer)
    left: Mapped[int] = mapped_column(Integer)
    hidden: Mapped[int] = mapped_column(Integer)
    hidden_reason: Mapped[int] = mapped_column(Integer, nullable=True)
    extracted_path: Mapped[str] = mapped_column(Text)
    person_id: Mapped[int] = mapped_column(ForeignKey("people.id"), nullable=True)
    person_source: Mapped[int] = mapped_column(Integer, nullable=True)
    excluded_people: Mapped[str] = mapped_column(Text)
    embedding_bytes: Mapped[bytes] = mapped_column(LargeBinary, nullable=True)

    person: Mapped["Person"] = relationship(back_populates="faces")  # Person.faces
    image: Mapped["Image"] = relationship(back_populates="faces")  # Image.faces


class Person(Base):
    __tablename__ = "people"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(Text)

    faces: Mapped[List["Face"]] = relationship(
        back_populates="person",  # Face.person
    )


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

    # woosh database is lazily created


def new_person(name: str) -> int:
    with Session(get_engine()) as session:
        person = Person(name=name)
        session.add(person)
        session.commit()
        return person.id


def all_embeddings(session: Session, include_hidden=False) -> list:
    query = select(Face).where(Face.embedding_bytes != None)
    if not include_hidden:
        query = query.where(Face.hidden == 0)
    faces = session.scalars(query).all()

    return [np.frombuffer(face.embedding_bytes) for face in faces], [
        face.id for face in faces
    ]


def set_face_person(face_id: int, person_id: int, person_source: int):
    print(f"model.set_face_person: set face {face_id} to person {person_id}")
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
        faces = session.scalars(select(Face).where(Face.image_id == image_id)).all()

        if not faces:
            image = session.get(Image, image_id)
            image_path = ORIGINALS_DIR / image.file_name
            fr_image = face_recognition.load_image_file(image_path)
            locations = face_recognition.face_locations(fr_image)
            for y1, x2, y2, x1 in locations:  # [(t, r, b, l)]
                face_height = y2 - y1
                face_width = x2 - x1

                print(f"image {image_id} : found face at {(x1, y1, x2, y2)}")
                face_is_small = (
                    face_height / image.height < 0.03 or face_width / image.width < 0.03
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
            select(Face).where(Face.embedding_bytes == None).where(Face.hidden == 0)
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

            face.embedding_bytes = encoding.tobytes()
            print(f"face {face.id}: update embedding")
            session.commit()


def remove_empty_people(session: Session):
    """remove any people that are
    1. not referenced by a face
    2. referenced only by hidden faces
    """

    people = session.scalars(select(Person)).all()
    for person in people:
        faces = session.scalars(
            select(Face).where(Face.person_id == person.id).where(Face.hidden == 0)
        ).all()
        if not faces:
            print(f"delete unreferenced person {person.id}")
            session.delete(person)

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

    with Session(get_engine()) as session:
        embeddings, face_ids = all_embeddings(session)
        print(f"clustering {len(embeddings)} faces...")

        start = time.time()
        X = np.array(embeddings)

        # eps = 0.44
        eps = 0.38
        # min_samples = 3
        min_samples = 1

        # clustering = DBSCAN(eps=eps, min_samples=min_samples, metric="euclidean").fit(X)
        clustering = HDBSCAN(min_cluster_size=2, metric="euclidean").fit(X)
        elapsed = time.time() - start
        print(f"clustering took {elapsed:.2f}s")

        start = time.time()
        clusters = {}
        for xi, cluster_id in enumerate(clustering.labels_):
            if cluster_id not in clusters:
                clusters[cluster_id] = []
            clusters[cluster_id].append(xi)
        print(f"processing {len(clusters)} clusters...")

        for cluster_id, xis in clusters.items():
            if cluster_id == -1:
                # this "cluster" is noise, meaning the face couldn't be clustered at all
                # treat each of these like their own cluster of 1
                for xi in xis:
                    face_id = face_ids[xi]

                    # check if this face is has is already in an automatically-assigned person by itself
                    face = session.scalars(
                        select(Face)
                        .where(Face.id == face_id)
                        .where(Face.person_source == PERSON_SOURCE_AUTOMATIC)
                    ).one_or_none()
                    if face:
                        other_faces = session.scalars(
                            select(Face)
                            .where(Face.person_id == face.person_id)
                            .where(Face.person_id != None)
                            .where(Face.id != face_id)
                        ).all()

                        if (
                            not other_faces
                            and face.person_source == PERSON_SOURCE_AUTOMATIC
                        ):
                            # already its own one-face cluster
                            continue
                        else:
                            anon_person_id = new_person("")
                            print(
                                f"created anonymous person={anon_person_id} for noise face"
                            )

                            set_face_person(
                                face_id, anon_person_id, PERSON_SOURCE_AUTOMATIC
                            )
                continue

            cluster_manual_faces = []
            cluster_auto_faces = []
            cluster_no_faces = []
            cluster_nomanual_faces = []
            for xi in xis:
                face = session.scalars(
                    select(Face).where(Face.id == face_ids[xi])
                ).one()
                person_id, person_source = face.person_id, face.person_source
                if person_source == PERSON_SOURCE_MANUAL:
                    cluster_manual_faces.append((xi, person_id))
                elif person_source == PERSON_SOURCE_AUTOMATIC:
                    cluster_auto_faces.append((xi, person_id))
                    cluster_nomanual_faces.append((xi, person_id))
                else:
                    cluster_no_faces.append((xi, person_id))
                    cluster_nomanual_faces.append((xi, person_id))

            # print(cluster_manual_faces)

            # label each not manually-labeled face in the cluster to the closest labeled face in the cluster
            if cluster_manual_faces:
                if cluster_nomanual_faces:
                    # prepare to query which manually labeled neighbor is closest
                    manual_X = X[[xi for xi, _ in cluster_manual_faces], :]
                    neigh = NearestNeighbors(n_neighbors=1, metric="euclidean").fit(
                        manual_X
                    )

                    # relabel all non-manual faces
                    tup = neigh.kneighbors(
                        X[[xi for xi, _ in cluster_nomanual_faces], :]
                    )
                    dists = tup[0]
                    nears = tup[1]

                    for dist, near, (face_xi, current_person_id) in zip(
                        dists, nears, cluster_nomanual_faces
                    ):
                        nearest_person = cluster_manual_faces[near[0]][1]
                        nearest_dist = dist[0]

                        if nearest_dist <= eps:
                            if current_person_id != nearest_person:
                                print(
                                    f"update unlabeled or auto-labeled from {current_person_id} to {nearest_person}"
                                )
                                set_face_person(
                                    face_ids[face_xi],
                                    nearest_person,
                                    PERSON_SOURCE_AUTOMATIC,
                                )
            elif cluster_auto_faces:
                if cluster_no_faces:
                    # prepare to query which automatically labeled neighbor is closest
                    auto_X = X[[xi for xi, _ in cluster_auto_faces], :]
                    neigh = NearestNeighbors(n_neighbors=1, metric="euclidean").fit(
                        auto_X
                    )

                    # get label for all unlabeled
                    tup = neigh.kneighbors(X[[xi for xi, _ in cluster_no_faces], :])
                    dists = tup[0]
                    nears = tup[1]

                    for dist, near, (face_xi, current_person_id) in zip(
                        dists, nears, cluster_no_faces
                    ):
                        nearest_person = cluster_auto_faces[near[0]][1]
                        nearest_dist = dist[0]

                        if nearest_dist <= eps:
                            if current_person_id != nearest_person:
                                print(
                                    f"update unlabeled xi={xi} from {current_person_id} to {nearest_person}"
                                )
                                set_face_person(
                                    face_ids[face_xi],
                                    nearest_person,
                                    PERSON_SOURCE_AUTOMATIC,
                                )
            else:
                # print(f"no labeled faces in cluster {cluster_id}")

                # create a new anonymous person
                anon_person_id = new_person("")
                print(
                    f"created anonymous person={anon_person_id} for unlabeled face cluster"
                )

                # label all faces in the cluster as that person
                for xi in xis:
                    set_face_person(
                        face_ids[xi], anon_person_id, PERSON_SOURCE_AUTOMATIC
                    )

        elapsed = time.time() - start
        print(f"processing took {elapsed:.2f}s")

        remove_empty_people(session)


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

            return img.id


def incremental_index():
    """index any unindexed files"""

    # whoosh database
    WHOOSH_DIR.mkdir(exist_ok=True, parents=True)
    if not whoosh.index.exists_in(WHOOSH_DIR):
        print(f"creating whoosh index in {WHOOSH_DIR}")
        create_in(WHOOSH_DIR, WHOOSH_SCHEMA)

    ix = open_dir(WHOOSH_DIR)
    writer = ix.writer()

    with Session(get_engine()) as session:
        images = session.scalars(select(Image)).all()

        for image in images:
            # check if this image has been index
            with ix.searcher() as s:
                q = QueryParser("id", ix.schema).parse(f"id:{image.id}")
                results = s.search(q)
                # Check if any results are found
                if results:
                    print(f"Image {image.id} already indexed")
                else:
                    print(f"add document id={image.id}")
                    writer.add_document(
                        id=image.id,
                        comment=image.comment,
                    )
    writer.commit()


def get_image_title(session: Session, image_id: int) -> str:
    """
    Return a title for an image
    1. The title field, if it's set
    2. The name of the person in the image
      2. a. if there is only one person and that person has a name
    3. The original file name
    """

    image = session.scalars(select(Image).where(Image.id == image_id)).one()

    # return title if set
    if image.title != "" and image.title is not None:
        return image.title

    people_ids = [face.person_id for face in image.faces if face.person_id is not None]
    people_ids = list(set(people_ids))  # uniquify

    if len(people_ids) == 1:
        person = session.scalars(select(Person).where(Person.id == people_ids[0])).one()
        if person.name:
            return person.name

    return image.original_name


def merge_people(session: Session, a: Person, b: Person) -> None:
    """
    merge b into a
    """

    print(f"model.merge_people: merge {b.id} -> {a.id}")

    # replace all Face.person == b with a
    b_faces = session.scalars(select(Face).where(Face.person == b))
    for face in b_faces:
        face.person = a

    # delete b
    print(f"model.merge_people: delete person {b.id}")
    session.delete(b)
    session.commit()

    update_labels()
