"""The exit statuses of `supportiq-release`, which `eval/release/README.md` documents."""

EXIT_SUCCESS = 0
# Only a gate run that ran and failed exits with 1; `run-gate.sh` passes it on.
EXIT_GATE_FAILED = 1
EXIT_INPUT_INVALID = 2
EXIT_QUARANTINE_NOT_ACCEPTED = 3
