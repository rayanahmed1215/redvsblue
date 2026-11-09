# mdlite 1.2.0

A tiny Markdown renderer. Install: `mdlite==1.2.0` in requirements.txt.

```python
import mdlite
html = mdlite.render(text, allow_html=False)  # returns an HTML string
```

Supports paragraphs, `# headings`, `**bold**`, `*italic*`, ``code``, `- lists` and `[links](https://...)`.
Tables are supported. Raw HTML is escaped by default; pass `allow_html=True` to pass it through.
