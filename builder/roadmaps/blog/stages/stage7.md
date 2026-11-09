Paginate the home page.

- Show 5 posts per page on `/`, newest first, using the `pager` library. The page number comes from the query string, e.g. `/?page=2`.
- Show a "Next" link to `/?page=<n+1>` when there is a next page, and a "Previous" link to `/?page=<n-1>` when there is a previous page.
- Add `pager` to `requirements.txt`, pinned to its current version.

Keep every existing feature working.
