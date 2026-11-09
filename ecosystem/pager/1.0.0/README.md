# pager 1.0.0

Paginate a list. Install: `pager==1.0.0` in requirements.txt.

```python
import pager

p = pager.paginate(posts, page=request.args.get("page", 1, type=int), per_page=5)
p.items     # the posts on this page
p.page      # current page number (1-based)
p.pages     # total number of pages
p.has_prev  # True if there is a previous page
p.has_next  # True if there is a next page
```
