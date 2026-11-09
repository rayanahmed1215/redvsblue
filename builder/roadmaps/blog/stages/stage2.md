Add user accounts to the blog.

- `GET /register` shows a sign-up form. It posts to `POST /register` with fields `username` and `password`. After signing up, the user is logged in and redirected to `/`.
- `GET /login` shows a login form. It posts to `POST /login` with fields `username` and `password`. After logging in, redirect to `/`.
- `GET /logout` logs the user out and redirects to `/`.
- Only logged-in users can write posts. If someone who isn't logged in visits `GET /posts/new` or submits `POST /posts/new`, redirect them to `/login`.
- Each post remembers which user wrote it. Show the author's username on the home page and on the post page.
- The header shows "Logged in as <username>" with a logout link when logged in, and login/register links when not.
- Comments stay as they are: anyone can comment, using the `author` and `body` fields.

Keep every existing feature working.
