"""Hooks that run before a demo reset (`POST /demo/reset`).

Background work that writes to the database (camera replays, the job runner) registers a hook that stops or
drains it, so a reset never races a writer that would recreate rows from the previous scenario.
"""

from collections.abc import Callable

ResetHook = Callable[[], None]

_reset_hooks: list[ResetHook] = []


def register_reset_hook(hook: ResetHook) -> ResetHook:
    if hook not in _reset_hooks:
        _reset_hooks.append(hook)
    return hook


def unregister_reset_hook(hook: ResetHook) -> None:
    if hook in _reset_hooks:
        _reset_hooks.remove(hook)


def run_reset_hooks() -> None:
    for hook in list(_reset_hooks):
        hook()
