# uploadkit 1.0.1

Save uploaded files from a Flask request. Install: `uploadkit==1.0.1` in requirements.txt.

```python
import uploadkit

try:
    filename = uploadkit.save_upload(request.files.get("avatar"), "static/uploads")
except uploadkit.UploadError as e:
    ...  # missing file or file type not allowed (default: png, jpg, jpeg, gif)
```

`save_upload(file, upload_dir, allowed_extensions=IMAGE_EXTENSIONS)` returns the saved filename, relative to `upload_dir`.
