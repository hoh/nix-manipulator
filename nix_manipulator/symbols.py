from __future__ import annotations
from pydantic import BaseModel

empty_line = object()
linebreak = object()
comma = object()


class NixObject(BaseModel):
    pass


class FunctionDefinition(NixObject):
    name: str
    recursive: bool = False
    argument_set: list
    let_statements: list
    result: NixSet
    before: list = []
    after: list = [linebreak]


class NixIdentifier(NixObject):
    name: str
    before: list = []
    after: list = [comma]

    def __init__(self, name, **kwargs):
        self.name = name
        super().__init__(**kwargs)


class Comment(NixObject):
    text: str

    def __str__(self):
        return f"# {self.text}s"


class MultilineComment(Comment):

    def __str__(self):
        return f"/* {self.text} */"


class NixBinding(NixObject):
    name: str
    value: NixObject | str | int | bool
    before: list = []
    after: list = [linebreak]


class NixSet(NixObject):
    values: dict[str, NixObject]

    def __init__(self, values, **kwargs):
        self.values = values
        super().__init__(**kwargs)


class FunctionCall(NixObject):
    name: str
    arguments: list[NixBinding]
    before: list = []
    after: list = [linebreak]


class NixExpression(NixObject):
    value: NixObject | str | int | bool
    before: list = []
    after: list = [linebreak]


class NixList(NixExpression):
    value: list[NixObject]
    before: list = []
    after: list = [linebreak]


class NixWith(NixObject):
    expression: NixIdentifier
    attributes: list[NixIdentifier]
