"""Conversor de Markdown a HTML compatible con Plane CE (Tiptap/ProseMirror).

Expone: markdown_to_html().
No hace: red, disco ni estado; solo usa re y la biblioteca estándar.
"""

import re


def markdown_to_html(md: str) -> str:
    """
    Convierte Markdown a HTML compatible con Plane CE (Tiptap/ProseMirror).
    Sin dependencias externas — usa solo re y stdlib.
    """
    if not md or not md.strip():
        return "<p></p>"

    # Normalizar saltos de línea
    md = md.replace("\r\n", "\n").replace("\r", "\n")

    lines = md.split("\n")
    html_parts = []
    i = 0

    def escape(s):
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    def inline(s):
        """Aplica formato inline: bold, italic, inline-code, links."""
        # Inline code (antes que bold/italic para no procesar su interior)
        s = re.sub(r"`([^`]+)`", lambda m: f"<code>{escape(m.group(1))}</code>", s)
        # Bold+italic ***text***
        s = re.sub(r"\*\*\*(.+?)\*\*\*", r"<strong><em>\1</em></strong>", s)
        # Bold **text**
        s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
        # Italic *text* (no afecta ** ya procesado)
        s = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<em>\1</em>", s)
        # Strikethrough ~~text~~
        s = re.sub(r"~~(.+?)~~", r"<s>\1</s>", s)
        # Links [text](url)
        s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', s)
        return s

    while i < len(lines):
        line = lines[i]

        # Fenced code block ```lang ... ```
        fence_m = re.match(r"^```(\w*)", line)
        if fence_m:
            lang = fence_m.group(1) or ""
            code_lines = []
            i += 1
            while i < len(lines) and not lines[i].startswith("```"):
                code_lines.append(escape(lines[i]))
                i += 1
            code_body = "\n".join(code_lines)
            lang_attr = f' class="language-{lang}"' if lang else ""
            html_parts.append(f"<pre><code{lang_attr}>{code_body}</code></pre>")
            i += 1
            continue

        # Headings ## / # / ###
        h_m = re.match(r"^(#{1,6})\s+(.*)", line)
        if h_m:
            level = len(h_m.group(1))
            text = inline(escape(h_m.group(2)))
            html_parts.append(f"<h{level}>{text}</h{level}>")
            i += 1
            continue

        # Horizontal rule ---
        if re.match(r"^[-*_]{3,}\s*$", line):
            html_parts.append("<hr>")
            i += 1
            continue

        # Unordered list block (lines starting with - or *)
        if re.match(r"^[-*]\s+", line):
            items = []
            while i < len(lines) and re.match(r"^[-*]\s+", lines[i]):
                item_text = inline(escape(re.sub(r"^[-*]\s+", "", lines[i])))
                items.append(f"<li>{item_text}</li>")
                i += 1
            html_parts.append("<ul>" + "".join(items) + "</ul>")
            continue

        # Ordered list block (lines starting with 1. 2. etc)
        if re.match(r"^\d+\.\s+", line):
            items = []
            while i < len(lines) and re.match(r"^\d+\.\s+", lines[i]):
                item_text = inline(escape(re.sub(r"^\d+\.\s+", "", lines[i])))
                items.append(f"<li>{item_text}</li>")
                i += 1
            html_parts.append("<ol>" + "".join(items) + "</ol>")
            continue

        # Blockquote > text
        if re.match(r"^>\s*", line):
            bq_lines = []
            while i < len(lines) and re.match(r"^>\s*", lines[i]):
                bq_lines.append(inline(escape(re.sub(r"^>\s*", "", lines[i]))))
                i += 1
            html_parts.append("<blockquote><p>" + "<br>".join(bq_lines) + "</p></blockquote>")
            continue

        # Table (lines containing |)
        if "|" in line and i + 1 < len(lines) and re.match(r"^[|\s\-:]+$", lines[i + 1]):
            header_cells = [c.strip() for c in line.strip().strip("|").split("|")]
            i += 2  # skip separator line
            rows = []
            while i < len(lines) and "|" in lines[i]:
                row_cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                rows.append(row_cells)
                i += 1
            th = "".join(f"<th>{inline(escape(c))}</th>" for c in header_cells)
            tbody_rows = "".join(
                "<tr>" + "".join(f"<td>{inline(escape(c))}</td>" for c in row) + "</tr>"
                for row in rows
            )
            html_parts.append(f"<table><thead><tr>{th}</tr></thead><tbody>{tbody_rows}</tbody></table>")
            continue

        # Checkbox list item - [ ] / - [x]
        if re.match(r"^[-*]\s+\[[ xX]\]", line):
            items = []
            while i < len(lines) and re.match(r"^[-*]\s+\[[ xX]\]", lines[i]):
                checked = "x" in lines[i][3:5].lower()
                text = inline(escape(re.sub(r"^[-*]\s+\[[ xX]\]\s*", "", lines[i])))
                chk = ' checked=""' if checked else ""
                items.append(f'<li><input type="checkbox"{chk} disabled> {text}</li>')
                i += 1
            html_parts.append('<ul class="task-list">' + "".join(items) + "</ul>")
            continue

        # Empty line → paragraph break (ya manejado por acumulación)
        if not line.strip():
            i += 1
            continue

        # Paragraph: la primera línea siempre se consume (garantiza avance); luego las continuas
        para_lines = [inline(escape(line))]
        i += 1
        while i < len(lines) and lines[i].strip() and not re.match(
            r"^(#{1,6}\s|```|[-*]\s|>\s|\d+\.\s+|[|\-*_]{3})", lines[i]
        ):
            para_lines.append(inline(escape(lines[i])))
            i += 1
        html_parts.append("<p>" + "<br>".join(para_lines) + "</p>")

    return "\n".join(html_parts) or "<p></p>"
