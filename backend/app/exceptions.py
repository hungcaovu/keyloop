class NotFoundError(Exception):
    """Raised when a requested entity does not exist."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class ConflictError(Exception):
    """Raised when a resource already exists (e.g. duplicate VIN)."""

    def __init__(self, message: str, existing=None):
        self.message = message
        self.existing = existing
        super().__init__(message)


class ResourceUnavailableError(Exception):
    """Raised when a technician or bay is unavailable for the requested slot."""

    def __init__(self, message: str, next_available_slot=None):
        self.message = message
        self.next_available_slot = next_available_slot
        super().__init__(message)


class ValidationError(Exception):
    """Raised when business-rule validation fails (distinct from marshmallow schema errors)."""

    def __init__(self, message: str, field: str = None):
        self.message = message
        self.field = field
        super().__init__(message)


class NoAvailabilityError(Exception):
    """Raised when no slot is found within the search horizon."""

    def __init__(self, message: str = "No availability found within the search horizon."):
        self.message = message
        super().__init__(message)


class HoldExpiredError(Exception):
    """Raised when a PENDING hold's TTL has elapsed before confirmation."""

    def __init__(self, message: str = "The hold has expired. Please select a new time slot.", next_available_slot=None):
        self.message = message
        self.next_available_slot = next_available_slot
        super().__init__(message)


class InvalidStateError(Exception):
    """Raised when an operation is attempted on an appointment in an incompatible status."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)
