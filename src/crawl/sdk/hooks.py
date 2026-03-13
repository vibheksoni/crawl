"""Lightweight async hook helpers for SDK workflows."""

from __future__ import annotations

import inspect


async def run_hook(callback, *args, **kwargs) -> None:
    """Run a sync or async callback if provided.

    Args:
        callback: Hook callback.
        *args: Positional hook arguments.
        **kwargs: Keyword hook arguments.
    """
    if callback is None:
        return
    result = callback(*args, **kwargs)
    if inspect.isawaitable(result):
        await result


async def run_named_hook(hooks: dict | None, name: str, *args, **kwargs) -> None:
    """Run a named hook from a hook mapping.

    Args:
        hooks: Hook mapping.
        name: Hook name.
        *args: Positional hook arguments.
        **kwargs: Keyword hook arguments.
    """
    if not hooks:
        return
    await run_hook(hooks.get(name), *args, **kwargs)
