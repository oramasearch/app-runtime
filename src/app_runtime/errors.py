"""Errors reported before an App process starts serving traffic."""


class AppRuntimeError(Exception):
    """Base class for a runtime startup failure."""


class ConfigurationError(AppRuntimeError):
    """The operator environment or app.toml is invalid."""


class LoadError(AppRuntimeError):
    """The pinned repository revision cannot be loaded safely."""


class DependencyError(AppRuntimeError):
    """The App requests a dependency that is not baked into the runtime."""

