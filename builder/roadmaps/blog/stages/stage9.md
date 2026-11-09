Add an admin panel.

- The first user who ever registered is the admin.
- `GET /admin` (admin only) lists every user and every post. Each post has a delete button that submits `POST /admin/posts/<id>/delete`, which deletes the post and its comments and redirects to `/admin`.
- Anyone who isn't the admin, including logged-out visitors, gets a 403 Forbidden response from `/admin` and from `/admin/posts/<id>/delete`.
- Show an "Admin" link in the header for the admin.

Keep every existing feature working.
