"""Project-specific exception types."""


class GlebError(Exception):
    """Base exception for gleb."""


class BlenderNotFoundError(GlebError):
    """Raised when Blender executable cannot be found."""


class BlenderVersionError(GlebError):
    """Raised when Blender version is unsupported."""


class BlenderExecutionError(GlebError):
    """Raised when Blender subprocess execution fails."""


class BlenderOutputError(GlebError):
    """Raised when Blender output cannot be parsed."""
