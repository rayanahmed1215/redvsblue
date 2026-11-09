Add private messages between users.

- `GET /messages` (logged-in users; redirect to `/login` otherwise) shows the user's inbox: every message sent to them with the sender's username, each linking to `/messages/<id>`. It also shows a form that posts to `POST /messages` with fields `to` (a username) and `body`.
- `POST /messages` sends the message and redirects to `/messages`. If the `to` user doesn't exist, respond with status 400 and an error message.
- `GET /messages/<id>` shows one message. Only its sender and recipient may see it; anyone else gets 403 Forbidden.
- Show a "Messages" link in the header for logged-in users.

Keep every existing feature working.
