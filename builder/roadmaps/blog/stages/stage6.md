Let users upload an avatar picture.

- `GET /settings/avatar` shows an upload form for logged-in users (redirect to `/login` if not logged in). It posts to `POST /settings/avatar` with a file field named `avatar`.
- Save the file with the `uploadkit` library into the `static/uploads/` folder and remember the saved filename on the user. After uploading, redirect to `/`.
- Only images are allowed: if `uploadkit` rejects the file, respond with status 400 and an error message.
- On the post page, show the author's avatar next to their name as an `<img>` whose `src` is `/static/uploads/<filename>`.
- Add `uploadkit` to `requirements.txt`, pinned to its current version.

Keep every existing feature working.
