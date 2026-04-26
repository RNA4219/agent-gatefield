"""
psycopg2 availability handling for vector_store module.
"""

from typing import Any, Callable, Optional

# Try to import at module load time
_psycopg2 = None
_execute_values = None
_RealDictCursor = None

try:
    import psycopg2 as _psycopg2
    from psycopg2.extras import execute_values as _execute_values, RealDictCursor as _RealDictCursor
    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False

# Exports for patching (static values - patch with new=True/False which doesn't pass arg)
psycopg2 = _psycopg2
execute_values = _execute_values
RealDictCursor = _RealDictCursor


def get_psycopg2() -> Optional[Any]:
    return psycopg2


def get_execute_values() -> Optional[Callable]:
    return execute_values


def get_RealDictCursor() -> Optional[Any]:
    return RealDictCursor


def is_available() -> bool:
    return PSYCOPG2_AVAILABLE


__all__ = [
    'psycopg2',
    'execute_values',
    'RealDictCursor',
    'PSYCOPG2_AVAILABLE',
    'get_psycopg2',
    'get_execute_values',
    'get_RealDictCursor',
    'is_available',
]