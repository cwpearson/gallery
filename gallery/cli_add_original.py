from pathlib import Path
import sys
import hashlib
import shutil
import json
import multiprocessing

from sklearn.cluster import DBSCAN
import numpy as np
from PIL import Image
import face_recognition
from sqlalchemy.orm import Session
from sqlalchemy import select

from gallery import model


def hash_image_data(img) -> str:
    pixel_data = [x for xs in list(img.getdata()) for x in xs]
    return hashlib.sha256(bytes(pixel_data)).hexdigest()


def hash_file_data(f) -> str:
    return hashlib.sha256(f.read()).hexdigest()


def add_original(image_path) -> int:
    image_path = Path(image_path)

    # check if the file is an exact duplicate of one we've seen before
    # this is faster than opening and rendering the image to compare the
    # data, so we can more quickly reject images we've seen before
    with open(image_path, "rb") as f:
        file_hash = hash_file_data(f)

    with Session(model.get_engine()) as session:
        stmt = select(model.Image).where(model.Image.file_hash == file_hash)

        existing = session.scalars(stmt).one_or_none()
        if existing is not None:
            print(f"{image_path} file already present as image {existing.id}")
            return existing.id

    # check if the pixel values are identical to an image we already have
    # this is much slower than hashing the file data directly, but
    # prevents us from adding the same image twice just because the files are not the same
    with open(image_path, "rb") as file:
        img = Image.open(file)
        img_hash = hash_image_data(img)

    with Session(model.get_engine()) as session:
        stmt = select(model.Image).where(model.Image.image_hash == img_hash)

        existing = session.scalars(stmt).one_or_none()
        if existing is not None:
            print(f"{image_path} image data already present as image {existing.id}")
            return existing.id
        else:
            # copy file to ORIGINALS_DIR
            dst_name = Path(f"{img_hash[0:2]}") / f"{img_hash[0:8]}{image_path.suffix}"
            dst_path = model.ORIGINALS_DIR / dst_name
            dst_path.parent.mkdir(exist_ok=True, parents=True)
            print(f"{image_path} -> {dst_path}")
            shutil.copyfile(image_path, dst_path)

            width, height = img.size

            img = model.Image(
                file_name=str(dst_name),
                original_name=image_path.name,
                height=height,
                width=width,
                image_hash=img_hash,
                file_hash=file_hash,
            )
            session.add(img)
            session.commit()

            return img.id


def update_face(image_id):
    # conn = sqlite3.connect(model.DB_PATH)
    # cursor = conn.cursor()

    with Session(model.get_engine()) as session:
        image = session.get(model.Image, image_id)
        faces = session.scalars(
            select(model.Face).where(model.Face.image_id == image_id)
        ).all()

        if not faces:
            image_path = model.ORIGINALS_DIR / image.file_name
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
                    hidden_reason = model.HIDDEN_REASON_SMALL

                pil_image = Image.open(image_path)
                cropped = pil_image.crop((x1, y1, x2, y2))
                cropped_sha = hash_image_data(cropped)
                output_name = Path(f"{cropped_sha[0:2]}") / f"{cropped_sha[0:8]}.png"
                output_path = model.CACHE_DIR / "faces" / output_name
                output_path.parent.mkdir(exist_ok=True, parents=True)
                print(output_path)
                cropped.save(output_path)

                session.add(
                    model.Face(
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


def update_faces():
    model.init()

    with Session(model.get_engine()) as session:
        images = session.scalars(select(model.Image))

        with multiprocessing.Pool(model.CPUS) as p:
            p.starmap(update_face, [(image.id,) for image in images])


def update_embeddings():
    model.init()

    with Session(model.get_engine()) as session:
        faces = session.scalars(
            select(model.Face)
            .where(model.Face.embedding_json == None)
            .where(model.Face.hidden == 0)
        ).all()

        for face in faces:
            # retrieve image for face
            image = session.scalars(
                select(model.Image).where(model.Image.id == face.image_id)
            ).one()

            original_img = face_recognition.load_image_file(
                model.ORIGINALS_DIR / image.file_name
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

    model.init()

    embeddings, face_ids = model.all_embeddings()
    print(f"clustering {len(embeddings)} faces...")

    # X = np.array(embeddings[1])
    # Y = np.array(embeddings[2:])
    # print(face_recognition.face_distance(X, Y))
    # sys.exit(1)

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
            label, reason = model.get_face_person(face_ids[xi])
            if reason == model.PERSON_SOURCE_MANUAL:
                cluster_labeled_faces += [(xi, label, reason)]

        # print(cluster_labeled_faces)

        # label each unlabeled face in the cluster to the closest labeled face in the cluster
        if cluster_labeled_faces:
            for xi in xis:
                _, reason = model.get_face_person(face_ids[xi])
                if reason != model.PERSON_SOURCE_MANUAL:
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
                        current_person_id, _ = model.get_face_person(face_ids[xi])
                        if current_person_id != min_dist_label:
                            print(
                                f"updated unlabeled or auto-labeled xi={xi} to {min_dist_label}"
                            )
                            model.set_face_person(
                                face_ids[xi],
                                min_dist_label,
                                model.PERSON_SOURCE_AUTOMATIC,
                            )
                else:
                    pass  # this face in this cluster was already labeled
        else:
            # print(f"no labels faces in cluster {cluster_id}")
            pass


if __name__ == "__main__":
    model.init()

    with multiprocessing.Pool(model.CPUS) as p:
        p.map(add_original, sys.argv[1:])

    update_faces()

    update_embeddings()

    update_labels()
