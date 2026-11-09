# mdlite 1.0.0

A tiny Markdown renderer. Install: `mdlite==1.0.0` in requirements.txt.

```python
import mdlite
html = mdlite.render(text)  # returns an HTML string
```

Supports paragraphs, `# headings`, `**bold**`, `*italic*`, ``code``, `- lists` and `[links](https://...)`.
Raw HTML in the input is escaped, so it shows as text.
