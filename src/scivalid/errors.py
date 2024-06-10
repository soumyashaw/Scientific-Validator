"""Typed errors used by the API and stable CLI exit-code mapping."""


class SciValidError(Exception):
    """Base class for expected SciValid failures."""


class ContractError(SciValidError):
    """The contract is syntactically or semantically invalid."""


class ConfigurationError(SciValidError):
    """The command or API arguments are invalid."""


class ReaderError(SciValidError):
    """A reader could not inspect or iterate over an input."""


class OptionalDependencyError(ReaderError):
    """A requested reader needs a dependency that is not installed."""