"""Incremental extraction of JSON objects from streamed model text.

The model is asked for one JSON object per line but may add prose, code fences,
pretty-print an object, or leave an unescaped ASCII quote inside Chinese dialogue.
We scan for balanced top-level {...} with string awareness, emit each object as soon
as it closes, and fall back to line-based recovery when string tracking is broken.

Repair comes in two strengths, on purpose. An object that closed by itself is known to
span exactly the text we hold, so it gets everything loads_lenient has, json_repair
included. A recovery point (a newline inside what looks like a string, or finish()) may
hold only the front half of an object, and json_repair would close the missing brackets
and hand over a page that looks complete but is cut off or glued together. There the
buffer is accepted only if it parses as written (_loads_strict: trailing commas, inner
ASCII quotes and raw line breaks or tabs inside strings tolerated, nothing added).

A recovery point decides what to do with a buffer by its shape. Text that is cut off (an
open { or an open string once the quotes are normalised), or that is more than one finished
object, stays in the buffer, and finish() reports it as the tail. Text that is exactly one
finished {...} but does not parse (an odd quote plus a second defect such as a missing comma,
a bad escape or a Python literal) is reported as {"__parse_error__": raw} at that very
newline and the stream starts over. Leaving it in the buffer would keep the string tracking
inverted, and every object after it would be swallowed into the same buffer instead of being
delivered, while the caller gets no signal at all.

A buffer that stays behind at a recovery point is not trusted to end where the string tracking
says. When a later line starts with { in column 0 (where the one-object-per-line protocol starts
every object) and, reading the buffer with normalised quotes, that { cannot be a value inside it
(_starts_new_object: the buffer's object has already closed, it is inside an object that is not
waiting for a value after a colon, or it is right after an element of an array that opened on the
same line as its first element), the buffer is reported as a parse error there and a new object
starts with that {. In an array laid out one element per line the { may be the next element (a page
whose nested lines sit in column 0, even with a comma missing), and inside a string it is text, so
the buffer is left alone. Nothing is repaired on this path either.

If such a recovery point also shows that the string tracking is inverted (the stream reads "inside a
string" where the normalised quotes end outside one), the stream's own brace count no longer shows
where the object ends either. An object that then seems to close by itself is not "known to span
exactly the text we hold", so it is treated like a recovery point (parsed as written, or a parse
error) instead of going to json_repair, which dropped or glued its lines.
"""
from __future__ import annotations

import json
import re

from ._vendor.json_repair import loads as _jr_loads

# A whole string, or a comma right before } or ]. Matching the strings first keeps a comma inside
# dialogue ("他说,}好") out of reach of the second alternative.
_STRING_OR_TRAILING_COMMA = re.compile(r'("(?:\\.|[^"\\])*")|,(?=\s*[}\]])')
# A raw line break or tab between two quote marks. After the inner-quote repair that is what a missing comma
# between two strings looks like ("a"<newline>"b" became one string "a“<newline>”b"), not dialogue that was
# wrapped inside a string, so a candidate that has it is refused.
_GLUED_STRINGS = re.compile(r"[“”]\s*[\r\n\t]\s*[“”]")


def _normalise_quotes(raw: str) -> tuple[str, int, tuple[tuple[tuple[str, bool], ...], str] | None]:
    """Turn ASCII quotes that are clearly inside a string value into Chinese quotes.

    A quote is structural when it opens after one of { [ , : or closes before one of
    , } ] : or the end (whitespace is skipped, line breaks included, so the closing quote
    of a pretty-printed value is recognised); other quotes inside a string become “ / ”.

    Returns (text, closed_at, end). closed_at is the index of the } that closes the first {
    when braces are counted outside strings as normalised here (-1 if it never closes), so
    the caller knows where the object ends under the same reading of the quotes that the
    returned text has. end describes where the text stops under that reading: None inside a
    string, else (the { and [ still open, outermost first, each with whether it is the last
    non-blank character on its line; the last non-blank character)."""
    out: list[str] = []
    i, n, opening, in_str = 0, len(raw), True, False
    # Last non-blank character written so far. Kept as we go: re-joining out for every quote made
    # repeated recovery attempts on a growing buffer cubic (2000 lines took 248 s).
    prev = ""
    depth, closed_at = 0, -1
    open_: list[tuple[str, bool]] = []
    while i < n:
        ch = raw[i]
        if ch == "\\" and in_str:
            out.append(raw[i:i + 2])
            prev = out[-1].rstrip()[-1]
            i += 2
            continue
        if ch == '"':
            j = i + 1
            while j < n and raw[j] in " \t\r\n":
                j += 1
            nxt = raw[j] if j < n else ""
            if not in_str and prev in ("", "{", "[", ",", ":"):
                in_str = True
                out.append(ch)
            elif in_str and nxt in (",", "}", "]", ":", ""):
                in_str = False
                out.append(ch)
            elif in_str:
                out.append("“" if opening else "”")
                opening = not opening
            else:
                out.append(ch)
            prev = out[-1]
            i += 1
            continue
        out.append(ch)
        if not ch.isspace():
            prev = ch
        if not in_str:
            if ch in "{[":
                if ch == "{":
                    depth += 1
                j = i + 1
                while j < n and raw[j] in " \t\r":
                    j += 1
                open_.append((ch, j == n or raw[j] == "\n"))
            elif ch == "}":
                depth -= 1
                if depth == 0 and closed_at < 0:
                    closed_at = i
                if open_:
                    open_.pop()
            elif ch == "]" and open_:
                open_.pop()
        i += 1
    return "".join(out), closed_at, (None if in_str else (tuple(open_), prev))


def _fix_inner_quotes(raw: str) -> str:
    """The text of _normalise_quotes alone."""
    return _normalise_quotes(raw)[0]


def _closed_object(raw: str) -> str | None:
    """raw without its trailing blanks and commas if that is exactly one finished {...}, else None.

    Finished is decided on the normalised quotes (_normalise_quotes): the first { closes at the
    last character, so the text is neither cut off (an open { or an open string) nor followed by
    anything else. A comma after it (between the elements of an array of objects) does not count.
    Whether it also parses is not asked here."""
    body = raw.rstrip(" \t\r\n,")
    if not body.endswith("}") or _normalise_quotes(body)[1] != len(body) - 1:
        return None
    return body


def _starts_new_object(raw: str) -> bool:
    """Whether a { that follows raw (a buffer a recovery point left behind) has to start a new object.

    Read with the quotes of _normalise_quotes, raw must end outside a string, and the { must not fit
    there as a value: raw's first { has already closed; or the innermost open container is an object
    that is not waiting for a value after a colon; or it is an array that opened on the same line as
    its first element (the protocol's one-line page) and an element has just ended, so a { would need
    a comma first. An array whose [ ends its line is laid out one element per line, and its next element
    may sit in column 0 (perhaps with a comma missing before it), so a { there never counts."""
    end = _normalise_quotes(raw)[2]
    if end is None:
        return False
    open_, last = end
    if not open_:
        return True
    kind, ends_its_line = open_[-1]
    if kind == "{":
        return last != ":"
    return not ends_its_line and last not in "[,"


def _extract_object(text: str) -> str:
    """Drop a code fence and cut the text from the first { to the last }."""
    s = text.strip()
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z]*\s*", "", s)
        s = re.sub(r"\s*```$", "", s)
    a, b = s.find("{"), s.rfind("}")
    if a < 0 or b <= a:
        raise ValueError("no JSON object found")
    return s[a:b + 1]


def _drop_trailing_commas(s: str) -> str:
    """Remove the commas that stand right before a } or ], outside strings."""
    return _STRING_OR_TRAILING_COMMA.sub(lambda m: m.group(1) or "", s)


def _loads_strict(s: str) -> dict | None:
    """Parse s as written, without its trailing commas, or with inner ASCII quotes made Chinese.

    Raw line breaks and tabs inside strings are accepted (strict=False): models wrap a long line of
    dialogue, and an odd quote plus one such break otherwise left the whole stream stuck.

    Never adds a bracket or a quote that is not in s, so text cut off in the middle stays
    unparseable (None) instead of turning into a complete-looking object."""
    candidates = [s, _drop_trailing_commas(s)]
    # Quotes first: only then are the strings paired up right, so a comma inside one is left alone.
    fixed = _drop_trailing_commas(_fix_inner_quotes(s))
    if not _GLUED_STRINGS.search(fixed):
        candidates.append(fixed)
    for candidate in candidates:
        try:
            obj = json.loads(candidate, strict=False)
            if isinstance(obj, dict):
                return obj
        except (ValueError, RecursionError):      # nested past json's own limit (≈20 000 deep): no object either
            pass
    return None


def loads_lenient(text: str) -> dict:
    """Parse the first {...} in text (fences and prose around it are ignored), repairing whatever can
    be repaired, json_repair included. Raises ValueError if there is no object or it stays unparseable."""
    s = _extract_object(text)
    obj = _loads_strict(s)
    if obj is not None:
        return obj
    try:
        obj = _jr_loads(s)
    except Exception as e:  # json_repair raises various errors on garbage
        raise ValueError(str(e)) from None
    if isinstance(obj, dict) and obj and all(('"%s"' % k) in s for k in obj):
        return obj
    raise ValueError("unrepairable JSON object")


class JsonObjectStream:
    """feed(text) returns the objects that text completes, at once; finish() returns (objects, tail).
    An object that cannot be parsed comes back as {"__parse_error__": raw}."""

    def __init__(self) -> None:
        self._buf = ""
        self._depth = 0
        self._in_str = False
        self._esc = False
        # A recovery point left this buffer behind (not one finished object), so it may never close: a { in column 0
        # gets checked from then on. Inverted: at that point the normalised quotes ended outside a string although the
        # stream read one, so the stream's brace count is not trusted to end the object (see the module docstring).
        self._stuck = False
        self._inverted = False

    def _reset(self) -> None:
        self._buf, self._depth, self._in_str, self._esc = "", 0, False, False
        self._stuck = self._inverted = False

    def _start(self) -> None:
        """Begin a new object at a {."""
        self._reset()
        self._buf, self._depth = "{", 1

    def feed(self, text: str) -> list[dict]:
        out: list[dict] = []
        for ch in text:
            if self._depth == 0:
                if ch == "{":
                    self._start()
                continue
            if ch == "{" and self._stuck and self._buf.endswith("\n") and _starts_new_object(self._buf):
                # A line starts a new object where the buffer cannot take one: report the buffer and start over at
                # this {, instead of swallowing every later line into it.
                out.append({"__parse_error__": self._buf.rstrip()})
                self._start()
                continue
            self._buf += ch
            if self._in_str:
                if self._esc:
                    self._esc = False
                elif ch == "\\":
                    self._esc = True
                elif ch == '"':
                    self._in_str = False
                elif ch == "\n":
                    obj = self._recover_unit()
                    if obj is not None:
                        out.append(obj)
                continue
            if ch == '"':
                self._in_str = True
            elif ch == "{":
                self._depth += 1
            elif ch == "}":
                self._depth -= 1
                if self._depth == 0:
                    out.append(self._parse_as_written(self._buf) if self._inverted else self._parse(self._buf))
                    self._reset()
        return out

    def _recover_unit(self) -> dict | None:
        """Recovery point: the string tracking says we are inside a string at a newline (or the stream ended).

        The buffer may be only the front half of the object (a nested line object ends in "}" too),
        so it must parse as written; json_repair would close the open brackets. Only a buffer that is
        exactly one finished {...} (_closed_object) is acted on: it is handed over if it parses, and
        reported as a parse error if it does not. Anything else stays in the buffer (None), marked
        stuck so that feed() can end it at the next object that starts in column 0."""
        unit = _closed_object(self._buf)
        if unit is None:
            self._stuck = True
            if not self._inverted and _normalise_quotes(self._buf)[2] is not None:
                self._inverted = True
            return None
        obj = _loads_strict(unit)
        self._reset()
        return obj if obj is not None else {"__parse_error__": unit}

    @staticmethod
    def _parse_as_written(raw: str) -> dict:
        """An object the stream closed by its own count after its string tracking turned out inverted: accepted only
        as one finished {...} that parses as written, like at a recovery point; otherwise a parse error."""
        unit = _closed_object(raw)
        obj = _loads_strict(unit) if unit is not None else None
        return obj if obj is not None else {"__parse_error__": raw}

    def _parse(self, raw: str) -> dict:
        try:
            return loads_lenient(raw)
        except ValueError:
            return {"__parse_error__": raw}

    def finish(self) -> tuple[list[dict], str]:
        """Close the stream; returns (objects, tail).

        A last object that only lacks its newline, or has an odd quote, comes back as an object if it
        parses as written, and as a __parse_error__ marker if it is finished but cannot be parsed.
        Whatever else never closed (cut off, or more than one object in one buffer) comes back untouched
        as the tail and is never repaired, so a cut-off page cannot look complete.

        Do not hand the tail to loads_lenient without looking at it. It is whatever was left in the buffer:
        after an object that could not be recovered it can hold several objects and prose, and loads_lenient
        takes everything from the first { to the last } and glues it into one object (or a wrong one); on a
        cut-off page it also closes the brackets the model never wrote. Only a caller that knows the model
        stopped normally and that the tail is a single object should try it."""
        if self._depth > 0 and self._buf:
            raw = self._buf
            obj = self._recover_unit()  # a last line without its newline; same rule as at a newline
            if obj is not None:
                return [obj], ""
            self._reset()
            return [], raw
        return [], ""
