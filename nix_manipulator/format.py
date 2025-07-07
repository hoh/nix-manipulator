from __future__ import annotations

from typing import Any, List

from nix_manipulator.expressions.comment import Comment, MultilineComment
from nix_manipulator.expressions.layout import comma, empty_line, linebreak


def _format_trivia(trivia_list: List[Any], indent: int = 0) -> str:
    """Convert trivia objects to string representation."""
    result = ""
    for item in trivia_list:
        if item is empty_line:
            result += "\n"
        elif item is linebreak:
            result += ""
        elif item is comma:
            result += ","
        elif isinstance(item, (Comment, MultilineComment)):
            result += item.rebuild(indent=indent) + "\n"
        else:
            raise NotImplementedError(f"Unsupported trivia item: {item}")
    return result
