class DependencyUnavailableError(Exception):
    """Transient: the same request may succeed later."""

    def __init__(self, *, error_code: str) -> None:
        super().__init__(error_code)
        self.error_code = error_code


class DependencyRejectedError(Exception):
    """Permanent: repeating the same request will fail the same way."""

    def __init__(self, *, error_code: str) -> None:
        super().__init__(error_code)
        self.error_code = error_code
