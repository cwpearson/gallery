from pathlib import Path
import sys
from os import getcwd


ORIGINALS_DIR = None
CACHE_DIR = Path(getcwd()) / ".gallery"


def update(originals_dir=None, cache_dir=None):

    if originals_dir:
        global ORIGINALS_DIR
        originals_dir = Path(originals_dir)

        if not originals_dir.is_dir():
            print(f"==== provided originals_dir {originals_dir} is not a directory")
            sys.exit(1)
        ORIGINALS_DIR = originals_dir

    if cache_dir:
        global CACHE_DIR
        cache_dir = Path(cache_dir)

        if not cache_dir.is_dir():
            print(f"==== provided cache_dir {cache_dir} is not a directory")
            sys.exit(1)
        CACHE_DIR = cache_dir
