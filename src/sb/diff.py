from typing import IO
import difflib

import click


def to_debug_string(s: bytes) -> str:
    """
    Converts a string to a hybrid representation:
    - Printable ASCII (32-126) -> stays as character
    - Everything else -> becomes \\xNN string
    """
    out = []
    # Work with the utf-8 bytes directly
    for b in s:
        if 32 <= b <= 126:
            out.append(chr(b))
        else:
            out.append(f"\\x{b:02x}")
    return "".join(out)


def get_printable_string_diff(
    str_a: str,
    str_b: str,
) -> tuple[str, str]:
    debug_a = str_a.encode("utf-8")
    debug_b = str_b.encode("utf-8")

    # 2. Diff the debug strings
    matcher = difflib.SequenceMatcher(None, debug_a, debug_b)

    line_a_parts = []
    line_b_parts = []

    for opcode, i1, i2, j1, j2 in matcher.get_opcodes():
        chunk_a = to_debug_string(debug_a[i1:i2])
        chunk_b = to_debug_string(debug_b[j1:j2])

        if opcode == "equal":
            line_a_parts.append(chunk_a)
            line_b_parts.append(chunk_b)

        elif opcode == "replace":
            # Highlight differences with background colors
            line_a_parts.append(click.style(chunk_a, bg="red"))
            line_b_parts.append(click.style(chunk_b, bg="green"))

        elif opcode == "delete":
            line_a_parts.append(click.style(chunk_a, bg="red"))
        elif opcode == "insert":
            line_b_parts.append(click.style(chunk_b, bg="green"))

    return "".join(line_a_parts), "".join(line_b_parts)


def print_string_diff(
    str_a: str,
    str_b: str,
    headings: tuple[str, str] = ("String A", "String B"),
    file: IO | None = None,
) -> None:
    a, b = get_printable_string_diff(str_a, str_b)

    click.echo(f"{headings[0]}: {a}", file=file)
    click.echo(f"{headings[1]}: {b}", file=file)


if __name__ == "__main__":
    # Example usage
    str_a = "cafér"
    str_b = "cafér"  # Note: 'é' is 'e' + combining acute accent

    a, b = get_printable_string_diff(str_a, str_b)

    print(f"String A: {a}")
    print(f"String B: {b}")
