from pathlib import Path
import sys
import sqlite3
import io
import hashlib
import shutil
import tkinter as tk
import json
import multiprocessing

from sklearn.cluster import DBSCAN
import numpy as np
from PIL import Image, ImageTk
import face_recognition

from gallery import model


def hash_image_data(img) -> str:
    pixel_data = [x for xs in list(img.getdata()) for x in xs]
    return hashlib.sha256(bytes(pixel_data)).hexdigest()


def add_original(image_path) -> int:
    model.init()

    image_path = Path(image_path)
    with open(image_path, "rb") as file:
        img = Image.open(file)
        sha_hash = hash_image_data(img)

    conn = sqlite3.connect(model.DB_PATH)
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM image_hashes WHERE sha_hash = ?", (sha_hash,))
    data = cursor.fetchone()

    if data is not None:
        image_id = data[0]
        print(f"{image_path} already present as image {image_id}")
    else:
        # copy to ORIGINALS_DIR
        dst_name = f"{sha_hash[0:8]}{image_path.suffix}"
        dst_path = model.ORIGINALS_DIR / dst_name
        dst_path.parent.mkdir(exist_ok=True, parents=True)
        print(f"{image_path} -> {dst_path}")
        shutil.copyfile(image_path, dst_path)

        cursor.execute(
            "INSERT INTO image_hashes (sha_hash, file_path, original_name) VALUES (?, ?, ?)",
            (sha_hash, dst_name, image_path.name),
        )
        conn.commit()
        image_id = cursor.lastrowid

    # Close the database connection
    conn.close()

    return image_id


def resize_to_fit(image, max_width, max_height):
    """
    Resize the image to fit within the specified dimensions while maintaining aspect ratio.
    """
    original_width, original_height = image.size

    ratio = min(max_width / original_width, max_height / original_height)
    new_size = (int(original_width * ratio), int(original_height * ratio))

    return image.resize(new_size, Image.Resampling.LANCZOS)


class ImageWindow:
    def __init__(self, file_path):
        self.file_path = file_path
        self.root = tk.Tk()
        self.root.title(file_path)
        self.root.minsize(400, 300)

        # Load the image using Pillow
        self.img_original = Image.open(file_path)

        # Create a label to display the image
        self.label = tk.Label(self.root)
        self.label.pack(
            fill=tk.BOTH,
            expand=tk.YES,
        )

        # Bind the configure event to dynamically resize the image
        self.label.bind("<Configure>", self.resize_image)

    def resize_image(self, event=None):
        print(f"in resize_image event={event}")
        new_width = self.label.winfo_width()
        new_height = self.label.winfo_height()

        print(event.width, event.height, new_width, new_height)

        # Resize the image using Pillow and update the label
        # there are probably some borders or something that cause the image to continually resize,
        # so just make this a bit smaller than the widget itself so it doesn't force it to get immediately larger
        img_resized = resize_to_fit(self.img_original, new_width - 4, new_height - 4)
        self.img_tk = ImageTk.PhotoImage(img_resized)
        self.label.config(image=self.img_tk)

    def show(self):
        # Wait for user input in the console
        # self.root.mainloop()
        user_input = input(f"Enter your input for the image {self.file_path}: ")
        print(f"Your input was: {user_input}")

        # Close the window after input
        self.root.destroy()


def update_face(image_id):
    conn = sqlite3.connect(model.DB_PATH)
    cursor = conn.cursor()
    image_row = cursor.execute(
        "SELECT id, file_path FROM image_hashes WHERE id = ?", (image_id,)
    ).fetchone()

    image_id, file_path = image_row

    face_rows = cursor.execute(
        "SELECT * from faces WHERE image_id = ?", (image_id,)
    ).fetchall()

    # window = ImageWindow(ORIGINALS_DIR / file_path)
    # window.show()

    if not face_rows:
        image = face_recognition.load_image_file(model.ORIGINALS_DIR / file_path)
        locations = face_recognition.face_locations(image)
        for y1, x2, y2, x1 in locations:  # [(t, r, b, l)]
            print(f"image {image_id}: found face at {(x1, y1, x2, y2)}")

            pil_image = Image.open(model.ORIGINALS_DIR / file_path)
            cropped = pil_image.crop((x1, y1, x2, y2))
            cropped_sha = hash_image_data(cropped)
            output_name = f"{cropped_sha[0:8]}.png"
            output_path = model.CACHE_DIR / "faces" / output_name
            output_path.parent.mkdir(exist_ok=True, parents=True)
            print(output_path)
            cropped.save(output_path)

            cursor.execute(
                "INSERT INTO faces (image_id, top, right, bottom, left, hidden, extracted_path) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (image_id, y1, x2, y2, x1, False, output_name),
            )

            # cropped.show()
        conn.commit()
    else:
        print(f"already detected faces for {image_id}")

    # Close the connection
    cursor.close()
    conn.close()


def update_faces():
    model.init()

    # Connect to the SQLite database
    conn = sqlite3.connect(model.DB_PATH)
    cursor = conn.cursor()

    # SQL query to select all rows from the image_hashes table
    image_rows = cursor.execute("SELECT id FROM image_hashes").fetchall()

    # Iterate over each row in the table
    with multiprocessing.Pool(model.CPUS) as p:
        p.starmap(update_face, [(image_id[0],) for image_id in image_rows])

    # Close the connection
    cursor.close()
    conn.close()


def update_embeddings():
    conn = sqlite3.connect(model.DB_PATH)
    cursor = conn.cursor()

    face_rows = cursor.execute(
        "SELECT id, image_id, top, right, bottom, left FROM faces WHERE embedding_json IS NULL"
    ).fetchall()

    for face_row in face_rows:
        face_id, image_id, top, right, bottom, left = face_row

        # retrieve image for face
        image_row = cursor.execute(
            "SELECT file_path from image_hashes WHERE id = ?", (image_id,)
        ).fetchone()
        file_path = image_row[0]

        # original_img = Image.open(ORIGINALS_DIR / file_path)
        # cropped = original_img.crop((left, top, right, bottom))
        # cropped.show()

        original_img = face_recognition.load_image_file(model.ORIGINALS_DIR / file_path)
        encoding = face_recognition.face_encodings(
            original_img, known_face_locations=[(top, right, bottom, left)]
        )[0]
        # print(encoding)

        data_str = json.dumps(encoding.tolist())

        print(f"face {face_id}: update embedding {data_str[:20]}...")
        cursor.execute(
            "UPDATE faces SET embedding_json = ? WHERE id = ?",
            (data_str, face_id),
        )
        conn.commit()

    # close connection
    cursor.close()
    conn.close()


def update_labels():
    """
    Cluster all the embeddings with DBSCAN
    This will produce a variety of clusters
    Each face in the cluster may be labeled
        - If so, assign each face in the cluster to the closest manually-labeled face in that cluster
        - Otherwise, create a new anonymous person and assign all faces in the cluster to that person
    """

    conn = sqlite3.connect(model.DB_PATH)
    cursor = conn.cursor()

    # get all embeddings

    # put through DBSCAN

    embeddings, face_ids = model.all_embeddings(conn)

    # X = np.array(embeddings[1])
    # Y = np.array(embeddings[2:])
    # print(face_recognition.face_distance(X, Y))
    # sys.exit(1)

    X = np.array(embeddings)

    clustering = DBSCAN(eps=0.41, min_samples=2, metric="euclidean").fit(X)
    # print(clustering.labels_)

    clusters = {}
    for xi, cluster_id in enumerate(clustering.labels_):
        clusters[cluster_id] = clusters.get(cluster_id, []) + [xi]

    print(clusters)

    for cluster_id, xis in clusters.items():
        if cluster_id == -1:
            continue

        print(f"processing cluster {cluster_id}")

        cluster_labeled_faces = []
        for xi in xis:
            label, reason = model.get_person(conn, face_ids[xi])
            if reason == model.PERSON_SOURCE_MANUAL:
                cluster_labeled_faces += [(xi, label, reason)]

        # print(cluster_labeled_faces)

        # label each unlabeled face to the closest labeled face
        if cluster_labeled_faces:
            for xi in xis:
                a, reason = model.get_person(conn, face_ids[xi])
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
                            if dist < min_dist:
                                min_dist_label = label
                                min_dist = dist

                    current_person_id, _ = model.get_person(conn, face_ids[xi])
                    if current_person_id != min_dist_label:
                        print(
                            f"updated unlabeled or auto-labeled xi={xi} to {min_dist_label}"
                        )
                        model.set_person(
                            conn,
                            face_ids[xi],
                            min_dist_label,
                            model.PERSON_SOURCE_AUTOMATIC,
                        )
                else:
                    pass  # this face in this cluster was already labeled
        else:
            # print(f"no labels faces in cluster {cluster_id}")
            pass

    cursor.close()
    conn.close()


if __name__ == "__main__":
    # encodings = []

    with multiprocessing.Pool(model.CPUS) as p:
        p.map(add_original, sys.argv[1:])

    update_faces()

    update_embeddings()

    update_labels()
