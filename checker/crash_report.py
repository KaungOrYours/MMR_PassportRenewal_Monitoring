"""Describes a crash without quoting it, for logs that are public.

GitHub Actions logs on this repo are world-readable, and an exception's message
can't be trusted there: a database error can quote the row it was writing, a
Telethon TypeNotFoundError embeds decrypted bytes, and a connection error can
name the database host and user. So nothing here ever calls str(exc). Only
exception types, schema metadata and checker/ file:line locations come out.
"""
import sys
from pathlib import Path

_PACKAGE_DIR = Path(__file__).resolve().parent


def _chain(exc: BaseException) -> list[BaseException]:
    """exc, followed by everything it was raised from or while handling."""
    chain: list[BaseException] = []
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        chain.append(current)
        current = current.__cause__ or (None if current.__suppress_context__ else current.__context__)
    return chain


def _deepest_checker_frame(exc: BaseException) -> str | None:
    location = None
    tb = exc.__traceback__
    while tb is not None:
        path = Path(tb.tb_frame.f_code.co_filename)
        if path.is_absolute() and path.is_relative_to(_PACKAGE_DIR):
            location = f"{_PACKAGE_DIR.name}/{path.relative_to(_PACKAGE_DIR).as_posix()}:{tb.tb_lineno}"
        tb = tb.tb_next
    return location


def describe_exception(exc: BaseException) -> str:
    """'OSError <- IntegrityError <- UniqueViolation at checker/main.py:12'.

    The location comes from the exception closest to the root cause that passed
    through checker/ code."""
    chain = _chain(exc)
    types = " <- ".join(type(e).__name__ for e in chain)
    location = next(filter(None, (_deepest_checker_frame(e) for e in reversed(chain))), "unknown location")
    return f"{types} at {location}"


def database_metadata(exc: BaseException) -> str:
    """SQLSTATE, table and constraint of a database error anywhere in the chain,
    or "". These are schema names. Diagnostics such as message_detail are never
    read, because that is where Postgres quotes row values."""
    for e in _chain(exc):
        source = getattr(e, "orig", None) or e
        diag = getattr(source, "diag", None)
        fields = (
            ("sqlstate", getattr(source, "pgcode", None)),
            ("table", getattr(diag, "table_name", None)),
            ("constraint", getattr(diag, "constraint_name", None)),
        )
        present = [f"{name} {value}" for name, value in fields if isinstance(value, str) and value]
        if present:
            return ", ".join(present)
    return ""


def _safe_excepthook(exc_type, exc, _tb) -> None:
    # This must not raise: Python answers a failing hook by printing the
    # original traceback, which is exactly what this exists to prevent.
    try:
        summary = describe_exception(exc)
    except Exception:
        summary = exc_type.__name__
    try:
        sys.stderr.write(f"Fatal: {summary}; detail withheld from this public log\n")
    except Exception:
        pass


def install_excepthook() -> None:
    """For entry points. Python still exits non-zero after this hook runs."""
    sys.excepthook = _safe_excepthook
