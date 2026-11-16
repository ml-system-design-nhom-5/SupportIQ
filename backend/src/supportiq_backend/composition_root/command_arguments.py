"""The arguments of the subcommands of `backend` that run a replica or a database command."""

from dataclasses import dataclass
from enum import StrEnum


class OneOffCommand(StrEnum):
    """The one-off database commands of `backend`, run as the database owner."""

    CREATE_APP_ROLE = "create-app-role"
    MIGRATE = "migrate"
    SEED = "seed"
    RESET = "reset"


@dataclass(frozen=True, slots=True)
class ServeArguments:
    """The arguments of `backend serve`.

    Attributes:
        host: The interface to listen on.
        port: The TCP port to listen on.
    """

    host: str
    port: int


@dataclass(frozen=True, slots=True)
class OneOffArguments:
    """The arguments of a one-off database command.

    Attributes:
        command: The command to run.
        is_confirmed: Whether `--yes` confirmed a reset in advance.
    """

    command: OneOffCommand
    is_confirmed: bool = False
