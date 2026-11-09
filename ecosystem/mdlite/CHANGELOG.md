## 2.0.0
- **Breaking:** `render()` has been renamed to `to_html()`. Update your calls.

## 1.2.0
- **Security:** raw HTML is now escaped by default (`allow_html=False`). In 1.1.0, raw HTML in user input was rendered as-is, which allows script injection (XSS). Pass `allow_html=True` only for trusted input.

## 1.1.0
- Added: tables (`| a | b |`).
- Added: raw HTML support, so authors can embed custom markup. Enabled by default (`allow_html=True`).

## 1.0.0
- First release: paragraphs, headings, bold, italic, code, lists and links.
