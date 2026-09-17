"""Permite `python -m cortador ...`, que es como lo lanza la app de escritorio."""

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
