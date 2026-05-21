"""Domain-specific exception types for unsubsetter."""


class UnsubsetterError(Exception):
    """Base class for all unsubsetter errors."""


class FontNotFoundError(UnsubsetterError):
    """A font referenced in the PDF could not be located on disk."""


class UnsupportedFontError(UnsubsetterError):
    """A font is of a type V1 doesn't handle (CFF, simple Type 1, etc.)."""


class VerificationError(UnsubsetterError):
    """Post-write verification of the output PDF failed."""
