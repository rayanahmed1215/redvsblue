# mdlite 1.1.0

A tiny Markdown renderer. Install: `mdlite==1.1.0` in requirements.txt.

```python
import mdlite
html = mdlite.render(text, allow_html=True)  # returns an HTML string
```

Supports paragraphs, `# headings`, `**bold**`, `*italic*`, ``code``, `- lists` and `[links](https://...)`.
Tables are supported. Raw HTML is passed through by default (`allow_html=True`), so authors can embed custom markup; pass `allow_html=False` to escape it.
