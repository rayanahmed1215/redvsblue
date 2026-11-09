"""uploadkit 1.0.1: save uploaded files from a Flask/Werkzeug request."""
import os
import re
import uuid

__version__ = "1.0.1"

IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "gif"}


class UploadError(Exception):
    """Raised when an upload is missing or has a file type that isn't allowed."""


def _clean_name(filename):
    name = os.path.basename(filename.replace("\\", "/"))
    name = re.sub(r"[^A-Za-z0-9._-]", "_", name).lstrip(".")
    return name or "upload"


def save_upload(file, upload_dir, allowed_extensions=IMAGE_EXTENSIONS):
    """Save `file` (a werkzeug FileStorage, e.g. request.files["avatar"]) into `upload_dir`.

    Returns the saved filename (relative to upload_dir). Raises UploadError for a missing file or a
    disallowed extension.
    """
    if file is None or not file.filename:
        raise UploadError("no file uploaded")
    name = _clean_name(file.filename)
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext not in allowed_extensions:
        raise UploadError(f"file type .{ext} is not allowed")
    os.makedirs(upload_dir, exist_ok=True)
    stem = name.rsplit(".", 1)[0]
    name = f"{stem}-{uuid.uuid4().hex[:8]}.{ext}"
    file.save(os.path.join(upload_dir, name))
    return name
