"""uploadkit 1.0.0: save uploaded files from a Flask/Werkzeug request."""
import os

__version__ = "1.0.0"

IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "gif"}


class UploadError(Exception):
    """Raised when an upload is missing or has a file type that isn't allowed."""


def save_upload(file, upload_dir, allowed_extensions=IMAGE_EXTENSIONS):
    """Save `file` (a werkzeug FileStorage, e.g. request.files["avatar"]) into `upload_dir`.

    Returns the saved filename (relative to upload_dir). Raises UploadError for a missing file or a
    disallowed extension.
    """
    if file is None or not file.filename:
        raise UploadError("no file uploaded")
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in allowed_extensions:
        raise UploadError(f"file type .{ext} is not allowed")
    os.makedirs(upload_dir, exist_ok=True)
    dest = os.path.join(upload_dir, file.filename)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    file.save(dest)
    return file.filename
