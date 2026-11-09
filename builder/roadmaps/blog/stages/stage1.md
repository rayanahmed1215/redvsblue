Build a small blog website using Python, Flask and SQLite.

Features:
- `GET /` lists all posts (newest first). Each post title links to `/posts/<id>`.
- `GET /posts/new` shows a form to write a post. The form posts to `POST /posts/new` with fields `title` and `body`. After saving, redirect to the new post's page.
- `GET /posts/<id>` shows the post's title and body, all of its comments, and a form to add a comment.
- The comment form posts to `POST /posts/<id>/comments` with fields `author` and `body`. After saving, redirect back to the post's page.
- Make it look nice: a simple shared layout with a header and some CSS.

Technical requirements:
- `app.py` must define the Flask application as a module-level variable named `app`.
- Store data in a SQLite file named `blog.db` in the current directory, and create the tables automatically when the app starts if they don't exist.
- Put HTML templates in a `templates/` folder.
- Only use Flask and the Python standard library.

