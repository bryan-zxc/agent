"""
Database infrastructure package.
Handles all database connections, sessions, and data access patterns.
"""

from .connection import DatabaseConfig

__all__ = ["DatabaseConfig"]