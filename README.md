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
  - [ ] Rename
  - [x] Delete
  - [x] Edit whether a detected face is actually this person
  - [x] Assignging a name to a face of an anonymous person will cause that face cluster to all be marked as that person, and then the empty anonymous person will be garbage-collected and the redirect back to the person page will fail because that person has been deleted
    - [ ] make a person page to a non-existent person redirect to /people?
- [ ] Merge people from GUI
- [ ] "People" Page
  - [x] sort by number of people
  - [x] Little thumbnail by each person
  - [x] show anonymous people as well
- [ ] "Image" page
  - [x] Don't error out if not
  - [x] Visible Faces
    - [x] Assign person to face
    - [x] Display person's name instead of ID if 
    assigned
    - [ ] add a "hide" button
  - [x] Hidden Faces
    - [ ] add an unhide button
  - [x] Delete
- [x] use the `not_people_json` field of `faces` table to store ids of people the user has said this face is not
  - [ ] when auto-labeling, find the closest labeled face that is not one of these people
- [x] create subdirectories in the .gallery folder for images so each one doesn't have too many files
- [x] auto-hide small faces
  - [x] store original size