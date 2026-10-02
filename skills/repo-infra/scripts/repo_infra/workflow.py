"""Read the block-style YAML that GitHub workflows are written in (D30).

The scripts use the standard library only, so PyYAML is not available here.
This reader covers what workflows use: block mappings and sequences, plain
and quoted scalars, single-line flow sequences, and literal and folded block
scalars. Every scalar comes back as a string, the way yaml.BaseLoader returns
it, and tests/test_workflow.py holds the two readers to the same result on
every workflow in this repository. Anchors, aliases, tags, flow mappings,
tabs and explicit indentation indicators raise ReadError: check then reports
the file as unreadable instead of guessing what it says.
"""

import re
from collections import namedtuple


class ReadError(Exception):
    """The text uses YAML this reader does not follow; the message says where."""


Interface = namedtuple("Interface", "inputs secrets outputs")

# A key is quoted, or plain up to the first `:` that ends the line or is
# followed by a space. A plain key cannot start with a YAML indicator.
_KEY = re.compile(
    r"""^(?P<key>"(?:[^"\\]|\\.)*"|'(?:[^']|'')*'|[^\s"'#\[\]{},&*!|>%@`-][^#]*?)"""
    r"""\s*:(?:[ ]+(?P<rest>.*))?$""")
_BLOCK = re.compile(r"^([|>])([+-]?)$")
_ESCAPES = {"n": "\n", "t": "\t", "\\": "\\", '"': '"', "/": "/", "0": "\0", " ": " "}


def _item(text):
    return text == "-" or text.startswith("- ")


def _quote_end(text):
    """The index just past the closing quote of `text`, or None."""
    quote, i = text[0], 1
    while i < len(text):
        if quote == '"' and text[i] == "\\":
            i += 2
            continue
        if text[i] == quote:
            if quote == "'" and text[i + 1:i + 2] == "'":
                i += 2
                continue
            return i + 1
        i += 1
    return None


def _unquote(text, line=0):
    if text[:1] == "'":
        return text[1:-1].replace("''", "'")
    if text[:1] != '"':
        return text
    body, out, i = text[1:-1], [], 0
    while i < len(body):
        if body[i] == "\\":
            escape = body[i + 1:i + 2]
            if escape not in _ESCAPES:
                raise ReadError(f"line {line}: the escape \\{escape}, which this reader "
                                "does not follow")
            out.append(_ESCAPES[escape])
            i += 2
        else:
            out.append(body[i])
            i += 1
    return "".join(out)


def _value(rest, line):
    """The value text after `key:` or `-`, without its trailing comment."""
    text = rest.strip()
    if not text or text.startswith("#"):
        return ""
    if text[0] in "'\"":
        end = _quote_end(text)
        if end is None:
            raise ReadError(f"line {line}: a quoted value that continues on the next line")
        tail = text[end:].strip()
        if tail and not tail.startswith("#"):
            raise ReadError(f"line {line}: text after a quoted value")
        return text[:end]
    cut = text.find(" #")
    return (text[:cut] if cut >= 0 else text).rstrip()


def _refuse(text, line):
    if text[0] in "&*":
        raise ReadError(f"line {line}: an anchor or alias; write the value out in full")
    if text[0] == "!":
        raise ReadError(f"line {line}: a tag; write the value without it")
    if text[0] == "{":
        raise ReadError(f"line {line}: a flow mapping; write it in block style")
    if text[0] in "|>" and not _BLOCK.match(text):
        raise ReadError(f"line {line}: a block scalar header this reader does not follow")


def _flow(text, line):
    """A flow sequence of scalars on one line: `[a, 'b']`."""
    if not text.endswith("]"):
        raise ReadError(f"line {line}: a flow sequence that does not end on its line")
    items, current, quote = [], "", None
    for char in text[1:-1]:
        if quote:
            current += char
            if char == quote:
                quote = None
            continue
        if char in "'\"":
            quote = char
            current += char
        elif char in "[]{}":
            raise ReadError(f"line {line}: a nested flow collection; write it in block style")
        elif char == ",":
            items.append(current.strip())
            current = ""
        else:
            current += char
    items.append(current.strip())
    return [_unquote(item, line) for item in items if item != ""]


def _fold(lines):
    """Folded style (YAML 1.2, 8.1.3): a break between two plain lines becomes
    a space; blank lines and more-indented lines keep their breaks."""
    out, last, blanks = "", None, 0
    for line in lines:
        if line == "":
            blanks += 1
            continue
        if last is None:
            out = "\n" * blanks + line
        elif blanks:
            spaced = line.startswith(" ") or last.startswith(" ")
            out += "\n" * (blanks + (1 if spaced else 0)) + line
        elif line.startswith(" ") or last.startswith(" "):
            out += "\n" + line
        else:
            out += " " + line
        last, blanks = line, 0
    return out


class _Reader:
    def __init__(self, text):
        self.lines = text.split("\n")
        self.i = 0

    def peek(self):
        """(indent, text) of the next line with content, or None at the end."""
        while self.i < len(self.lines):
            raw = self.lines[self.i]
            text = raw.strip()
            if text and not text.startswith("#") and text not in ("---", "..."):
                lead = raw[:len(raw) - len(raw.lstrip())]
                if "\t" in lead:
                    raise ReadError(f"line {self.i + 1}: a tab in the indentation")
                return len(lead), text
            self.i += 1
        return None

    def node(self, indent):
        _, text = self.peek()
        return self.sequence(indent) if _item(text) else self.mapping(indent)

    def mapping(self, indent):
        result = {}
        while True:
            peeked = self.peek()
            if peeked is None or peeked[0] < indent:
                return result
            at, text = peeked
            line = self.i + 1
            if at > indent:
                raise ReadError(f"line {line}: indented deeper than the key above it")
            if _item(text):
                return result
            match = _KEY.match(text)
            if match is None:
                raise ReadError(f"line {line}: expected `key: value`")
            key = _unquote(match["key"], line)
            if key in result:
                raise ReadError(f"line {line}: the key {key} appears twice")
            self.i += 1
            result[key] = self.value(match["rest"] or "", indent, line, in_mapping=True)

    def sequence(self, indent):
        result = []
        while True:
            peeked = self.peek()
            if peeked is None or peeked[0] != indent or not _item(peeked[1]):
                return result
            line = self.i + 1
            rest = peeked[1][1:]
            inner = indent + 1 + len(rest) - len(rest.lstrip(" "))
            rest = rest.strip()
            if rest and not rest.startswith("#") and (_item(rest) or _KEY.match(rest)):
                # The item's content starts on the dash line: read the line
                # again with the dash turned into indentation.
                self.lines[self.i] = " " * inner + rest
                result.append(self.node(inner))
            else:
                self.i += 1
                result.append(self.value(rest, indent, line, in_mapping=False))

    def value(self, rest, indent, line, in_mapping):
        text = _value(rest, line)
        if text == "":
            peeked = self.peek()
            if peeked is not None and peeked[0] > indent:
                return self.node(peeked[0])
            if (in_mapping and peeked is not None and peeked[0] == indent
                    and _item(peeked[1])):
                return self.sequence(indent)
            return ""
        if text.replace(" ", "") == "{}":
            return {}
        _refuse(text, line)
        if text[0] == "[":
            return _flow(text, line)
        block = _BLOCK.match(text)
        if block:
            return self.block(indent, block[1], block[2])
        if text[0] in "'\"":
            return _unquote(text, line)
        parts = [text]
        while True:
            peeked = self.peek()
            if peeked is None or peeked[0] <= indent:
                return " ".join(parts)
            parts.append(_value(peeked[1], self.i + 1))
            self.i += 1

    def block(self, indent, style, chomp):
        lines, width = [], None
        while self.i < len(self.lines):
            raw = self.lines[self.i]
            if raw.strip() == "":
                lines.append("")
                self.i += 1
                continue
            lead = len(raw) - len(raw.lstrip(" "))
            if width is None:
                if lead <= indent:
                    break
                width = lead
            if lead < width:
                break
            lines.append(raw[width:])
            self.i += 1
        trailing = 0
        while lines and lines[-1] == "":
            lines.pop()
            trailing += 1
        if not lines:
            return ""
        body = "\n".join(lines) if style == "|" else _fold(lines)
        if chomp == "-":
            return body
        if chomp == "+":
            return body + "\n" * (1 + trailing)
        return body + "\n"


def load(text):
    """The document in `text`: dicts, lists and strings; None when it is empty."""
    reader = _Reader(text)
    peeked = reader.peek()
    if peeked is None:
        return None
    return reader.node(peeked[0])


def _table(call, key):
    entries = call.get(key) if isinstance(call, dict) else None
    if not isinstance(entries, dict):
        return {}
    return {name: spec if isinstance(spec, dict) else {} for name, spec in entries.items()}


def interface(doc):
    """What a reusable workflow takes and gives, or None if it is not one."""
    on = doc.get("on") if isinstance(doc, dict) else None
    if on == "workflow_call" or (isinstance(on, list) and "workflow_call" in on):
        return Interface({}, {}, ())
    if not isinstance(on, dict) or "workflow_call" not in on:
        return None
    call = on["workflow_call"]
    inputs = {name: {"required": str(spec.get("required", "")).lower() == "true",
                     "default": spec.get("default"),
                     "type": spec.get("type", ""),
                     "description": spec.get("description", "")}
              for name, spec in _table(call, "inputs").items()}
    secrets = {name: {"required": str(spec.get("required", "")).lower() == "true",
                      "description": spec.get("description", "")}
               for name, spec in _table(call, "secrets").items()}
    return Interface(inputs, secrets, tuple(_table(call, "outputs")))
