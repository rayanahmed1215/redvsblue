# mdlite 2.0.0

A tiny Markdown renderer. Install: `mdlite==2.0.0` in requirements.txt.

```python
import mdlite
html = mdlite.to_html(text)  # returns an HTML string
```

Supports paragraphs, `# headings`, `**bold**`, `*italic*`, ``code``, `- lists`, `[links](https://...)` and tables.
Raw HTML is escaped by default; pass `allow_html=True` to pass it through.

**`render()` was removed in 2.0.0. Use `to_html()`.**
