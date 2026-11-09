Add tags and search.

- The new-post and edit-post forms get a `tags` field: a comma-separated list such as `python, flask`. Store tags lowercase with surrounding spaces removed.
- Show each post's tags on the home page and the post page, each linking to `/tags/<tag>`.
- `GET /tags/<tag>` lists all posts with that tag (title linking to the post).
- `GET /search?q=<words>` lists all posts whose title or body contains the search text (case-insensitive). Add a search box to the shared header.

Keep every existing feature working.
