# 

## Example

```bash
python -m gallery.cli_add_original example_originals/*
python -m sanic gallery.server:app --debug
```

Then navigate to http://localhost:8000 in your browser.

## Add Images
```
python -m gallery.cli_add_original /path/to/images/*
```

## Launch Gallery
```
python -m gallery.server
```
Browse to http://localhost:8000

## Roadmap


- [x] How to fix that the path includes things like `/gallery/server` because that's the python package name
- [x] Track time original was added
- [x] Upload images from GUI
 - [x] Detect faces after upload
- [x] "Bulk Label"
  - [x] Paginate
- [ ] "Person" page
  - [ ] Change name
  - [ ] Delete
  - [x] Edit whether a detected face is actually this person
- [ ] Merge people from GUI
- [ ] "People" Page
  - [ ] Little thumbnail by each person
- [ ] "Image" page
  - [x] Don't error out if not
  - [x] Visible Faces
    - [x] Assign person to face
    - [x] Display person's name instead of ID if assigned
  - [x] Hidden Faces
  - [x] Delete
- [x] use the `not_people_json` field of `faces` table to store ids of people the user has said this face is not
  - [ ] when auto-labeling, find the closest labeled face that is not one of these people
- [x] create subdirectories in the .gallery folder for images so each one doesn't have too many files
- [x] auto-hide small faces
  - [x] store original size