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


def add_original(image_path) -> int:
    model.init()

    image_path = Path(image_path)
    with open(image_path, "rb") as file:
        img = Image.open(file)
        pixel_data = [x for xs in list(img.getdata()) for x in xs]
        # img_byte_arr = io.BytesIO()
        # img.save(img_byte_arr, format="png")
        sha_hash = hashlib.sha256(bytes(pixel_data)).hexdigest()

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
            "INSERT INTO image_hashes (sha_hash, file_path) VALUES (?, ?)",
            (sha_hash, dst_name),
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
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    image_row = cursor.execute(
        "SELECT * FROM image_hashes WHERE id = ?", (image_id,)
    ).fetchone()

    image_id, sha_hash, file_path = image_row

    face_rows = cursor.execute(
        "SELECT * from image_faces WHERE image_id = ?", (image_id,)
    ).fetchall()

    # window = ImageWindow(ORIGINALS_DIR / file_path)
    # window.show()

    if not face_rows:
        image = face_recognition.load_image_file(ORIGINALS_DIR / file_path)
        locations = face_recognition.face_locations(image)
        for y1, x2, y2, x1 in locations:  # [(t, r, b, l)]
            print(f"image {image_id}: found face at {(x1, y1, x2, y2)}")
            cursor.execute(
                "INSERT INTO image_faces (image_id, top, right, bottom, left, hide) VALUES (?, ?, ?, ?, ?, ?)",
                (image_id, y1, x2, y2, x1, False),
            )
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
    image_rows = cursor.execute("SELECT * FROM image_hashes").fetchall()

    # Iterate over each row in the table
    with multiprocessing.Pool(model.CPUS) as p:
        p.starmap(
            update_face, [(image_id,) for image_id, sha_hash, file_path in image_rows]
        )

    # Close the connection
    cursor.close()
    conn.close()


def update_embeddings():
    conn = sqlite3.connect(model.DB_PATH)
    cursor = conn.cursor()

    results = cursor.execute("SELECT * from image_faces").fetchall()

    for face_row in results:
        face_id, image_id, top, right, bottom, left, hide = face_row

        # retrieve image for face
        image_row = cursor.execute(
            "SELECT * from image_hashes WHERE id = ?", (image_id,)
        ).fetchone()
        _, sha_hash, file_path = image_row

        # original_img = Image.open(ORIGINALS_DIR / file_path)
        # cropped = original_img.crop((left, top, right, bottom))
        # cropped.show()

        results = cursor.execute(
            "SELECT * from face_embeddings WHERE face_id = ?", (face_id,)
        ).fetchall()

        if not results:
            original_img = face_recognition.load_image_file(ORIGINALS_DIR / file_path)
            encoding = face_recognition.face_encodings(
                original_img, known_face_locations=[(top, right, bottom, left)]
            )[0]
            # print(encoding)

            data_str = json.dumps(encoding.tolist())
            # print(data_str)

            print(f"face {face_id}: store embedding {data_str[:20]}...")
            cursor.execute(
                "INSERT INTO face_embeddings (face_id, embedding_json) VALUES (?, ?)",
                (face_id, data_str),
            )
            conn.commit()
        else:
            print(f"already have embedding for face {face_id}")

    # close connection
    cursor.close()
    conn.close()


if __name__ == "__main__":
    # encodings = []

    with multiprocessing.Pool(model.CPUS) as p:
        p.map(add_original, sys.argv[1:])

    update_faces()
    #     print(locations)
    #     new_encodings = face_recognition.face_encodings(
    #         image, known_face_locations=locations
    #     )
    #     encodings += new_encodings

    update_embeddings()

    # print(len(encodings))
    # X = np.array(encodings)
    # clustering = DBSCAN(eps=0.41, metric="euclidian").fit(X)

    # print(clustering.labels_)
