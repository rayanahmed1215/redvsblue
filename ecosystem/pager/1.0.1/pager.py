"""pager 1.0.1: paginate a list."""
from dataclasses import dataclass

__version__ = "1.0.1"


@dataclass
class Page:
    items: list
    page: int
    pages: int
    has_prev: bool
    has_next: bool


def paginate(items, page=1, per_page=10):
    """Return the given page (1-based) of `items`. Pages outside the range are clamped."""
    items = list(items)
    pages = max(1, -(-len(items) // per_page))
    page = min(max(1, int(page)), pages)
    start = (page - 1) * per_page
    return Page(items[start:start + per_page], page, pages, page > 1, page < pages)
