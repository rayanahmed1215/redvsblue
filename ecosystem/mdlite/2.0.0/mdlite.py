"""mdlite 2.0.0: a tiny Markdown renderer."""
import html
import re

__version__ = "2.0.0"


def _inline(text):
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"\*([^*]+)\*", r"<em>\1</em>", text)

    def link(m):
        url = m.group(2)
        if not re.match(r"^(https?://|/)", url):
            return m.group(1)
        return f'<a href="{url.replace(chr(34), "&quot;")}">{m.group(1)}</a>'
    return re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", link, text)


def _table(lines, esc):
    rows = [[c.strip() for c in l.strip().strip("|").split("|")] for l in lines]
    head, body = rows[0], [r for r in rows[2:]]
    th = "".join(f"<th>{_inline(esc(c))}</th>" for c in head)
    trs = "".join("<tr>" + "".join(f"<td>{_inline(esc(c))}</td>" for c in r) + "</tr>" for r in body)
    return f"<table><thead><tr>{th}</tr></thead><tbody>{trs}</tbody></table>"


def to_html(text, allow_html=False):
    """Convert Markdown to HTML. Raw HTML in the input is escaped unless allow_html=True."""
    esc = (lambda s: s) if allow_html else (lambda s: html.escape(s, quote=False))
    out = []
    for block in re.split(r"\n\s*\n", (text or "").strip()):
        lines = block.splitlines()
        if not lines:
            continue
        heading = re.match(r"^(#{1,6})\s+(.*)$", lines[0])
        if heading and len(lines) == 1:
            n = len(heading.group(1))
            out.append(f"<h{n}>{_inline(esc(heading.group(2)))}</h{n}>")
        elif len(lines) >= 2 and all(l.strip().startswith("|") for l in lines) and re.match(r"^\|?[\s:|-]+$", lines[1]):
            out.append(_table(lines, esc))
        elif all(re.match(r"^[-*]\s+", l) for l in lines):
            items = "".join(f"<li>{_inline(esc(re.sub(r'^[-*]\s+', '', l)))}</li>" for l in lines)
            out.append(f"<ul>{items}</ul>")
        else:
            out.append("<p>" + "<br>\n".join(_inline(esc(l)) for l in lines) + "</p>")
    return "\n".join(out)
