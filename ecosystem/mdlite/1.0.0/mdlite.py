"""mdlite 1.0.0: a tiny Markdown renderer."""
import html
import re

__version__ = "1.0.0"


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


def render(text):
    """Convert Markdown to HTML. Raw HTML in the input is escaped."""
    out = []
    for block in re.split(r"\n\s*\n", (text or "").strip()):
        lines = block.splitlines()
        if not lines:
            continue
        esc = [_inline(html.escape(l, quote=False)) for l in lines]
        heading = re.match(r"^(#{1,6})\s+(.*)$", lines[0])
        if heading and len(lines) == 1:
            n = len(heading.group(1))
            out.append(f"<h{n}>{_inline(html.escape(heading.group(2), quote=False))}</h{n}>")
        elif all(re.match(r"^[-*]\s+", l) for l in lines):
            items = "".join(f"<li>{_inline(html.escape(re.sub(r'^[-*]\s+', '', l), quote=False))}</li>" for l in lines)
            out.append(f"<ul>{items}</ul>")
        else:
            out.append("<p>" + "<br>\n".join(esc) + "</p>")
    return "\n".join(out)
