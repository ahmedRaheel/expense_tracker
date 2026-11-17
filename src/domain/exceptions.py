"""Pure domain errors, independent of HTTP and SQLAlchemy."""

class DomainError(Exception):
    """A violated business invariant."""

class UnsupportedCurrency(DomainError):
    pass

class InvalidBudget(DomainError):
    pass