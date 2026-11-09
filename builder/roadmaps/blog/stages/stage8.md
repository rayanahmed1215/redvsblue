Add public user profiles.

- `GET /users/<username>` shows the user's name, their avatar (if they uploaded one), their bio rendered as Markdown with `mdlite`, and a list of their posts (titles linking to the posts). Respond with 404 for a username that doesn't exist.
- `GET /settings/profile` shows a form with a `bio` field for logged-in users (redirect to `/login` if not logged in). It posts to `POST /settings/profile`; save the bio and redirect to the user's profile page.
- On the post page and the home page, the author's username links to their profile.

Keep every existing feature working.
