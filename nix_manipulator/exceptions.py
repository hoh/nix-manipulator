class NixSyntaxError(SyntaxError):
    pass


class ResolutionError(Exception):
    """Raised when an identifier cannot be resolved within scope."""

    pass
