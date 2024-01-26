# 

## Example

```bash
python -m gallery.cli_add_original example_originals/*
python -m gallery.server
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

- [ ] Track time original was added
- [x] Upload images from GUI
- [ ] Edit person from GUI
  - [ ] Change name
  - [ ] Delete
- [ ] Merge people from GUI
- [ ] Image page
  - [ ] Labeled Faces
  - [ ] Unlabeled Faces
  - [ ] Hidden Faces
- [x] use the `not_people_json` field of `faces` table to store ids of people the user has said this face is not
  - [ ] when auto-labeling, find the closest labeled face that is not one of these people
- [x] create subdirectories in the .gallery folder for images so each one doesn't have too many files
- [x] auto-hide small faces
  - [x] store original size