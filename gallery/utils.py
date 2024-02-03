import sqlite3
import hashlib

from gallery import model

from PIL import Image as PilImage


def hash_image_data(img) -> str:
    pixel_data = [x for xs in list(img.getdata()) for x in xs]
    return hashlib.sha256(bytes(pixel_data)).hexdigest()


def hash_file_data(f) -> str:
    return hashlib.sha256(f.read()).hexdigest()


def input_yn(prompt: str) -> bool:
    while True:
        result = input(prompt + " [yYnN]\n")
        print(result)
        if result in ("y", "Y"):
            return True
        elif result in ("n", "N"):
            return False


def input_choices(l: list) -> int:
    prompt = "Enter an option:\n"
    for i, e in enumerate(l):
        prompt += f"\t{i}. {e}\n"

    while True:
        resp = input(prompt)
        try:
            resp_int = int(resp)
        except ValueError:
            continue
        if resp_int < len(l):
            return resp_int


def input_person_name(conn: sqlite3.Connection, prompt: str) -> int:
    while True:
        r_name = input(prompt + "\n")
        person_id = model.get_person_by_name_exact(conn, r_name)
        people_ids, people_names = model.get_people_by_name_near(conn, r_name)
        if person_id is not None:
            return person_id
        else:
            resp = input_choices([f"{r_name} (new person)"] + people_names)

            if resp == 0:
                return model.new_person(r_name)
            else:
                return people_ids[resp - 1]


def extension_for(img: PilImage) -> str:
    if img.format == "JPEG":
        return "jpg"
    elif img.format == "PNG":
        return "png"
    else:
        raise RuntimeError(f"unexpected format {img.format}")
