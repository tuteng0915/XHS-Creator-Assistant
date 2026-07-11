class ApplicationError(Exception):
    """Base class for errors that are safe to turn into API responses."""


class NotFoundError(ApplicationError):
    pass


class ConflictError(ApplicationError):
    pass


class ValidationError(ApplicationError):
    pass

