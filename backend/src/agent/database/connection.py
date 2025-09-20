"""
Database connection factory for PostgreSQL.
Uses settings for all configuration - single source of truth.
"""
import logging
from typing import Optional
from urllib.parse import quote_plus
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

from ..config.settings import settings

logger = logging.getLogger(__name__)


class DatabaseConfig:
    """
    Database configuration using Pydantic settings.
    This class wraps settings to provide database-specific functionality.
    """

    def __init__(self):
        """Initialise from settings - single source of truth."""
        self.settings = settings

        # Validate required fields at startup
        if not self.settings.postgres_password:
            raise ValueError("POSTGRES_PASSWORD must be set in environment")

    @property
    def project_database_name(self) -> str:
        """
        Get the database name for the current project.
        Project names are assumed to be valid PostgreSQL database names.
        """
        return self.settings.project_name

    def get_database_url(self, database_name: Optional[str] = None) -> str:
        """
        Generate PostgreSQL connection URL for async operations.

        Args:
            database_name: Optional database name override.
                          If not provided, uses project database name.

        Returns:
            PostgreSQL connection URL for asyncpg
        """
        # Use provided database or default to project database
        db_name = database_name or self.project_database_name

        # URL-encode the password to handle special characters
        encoded_password = quote_plus(self.settings.postgres_password)

        # Construct PostgreSQL URL for asyncpg
        database_url = (
            f"postgresql+asyncpg://{self.settings.postgres_user}:"
            f"{encoded_password}@{self.settings.postgres_host}:"
            f"{self.settings.postgres_port}/{db_name}"
        )

        logger.debug(f"Database URL configured for: {db_name}")
        return database_url

    def get_sync_database_url(self, database_name: Optional[str] = None) -> str:
        """
        Generate synchronous PostgreSQL connection URL (for Alembic migrations).

        Args:
            database_name: Optional database name override.

        Returns:
            PostgreSQL connection URL for psycopg2
        """
        # Use provided database or default to project database
        db_name = database_name or self.project_database_name

        # URL-encode the password
        encoded_password = quote_plus(self.settings.postgres_password)

        # Construct PostgreSQL URL for psycopg2
        database_url = (
            f"postgresql://{self.settings.postgres_user}:"
            f"{encoded_password}@{self.settings.postgres_host}:"
            f"{self.settings.postgres_port}/{db_name}"
        )

        return database_url

    def get_admin_database_url(self) -> str:
        """
        Get connection URL for the main/admin database.
        Used for creating project databases.

        Returns:
            PostgreSQL connection URL for the main database
        """
        encoded_password = quote_plus(self.settings.postgres_password)

        return (
            f"postgresql+asyncpg://{self.settings.postgres_user}:"
            f"{encoded_password}@{self.settings.postgres_host}:"
            f"{self.settings.postgres_port}/{self.settings.postgres_db}"
        )

    async def ensure_project_database_exists(self) -> None:
        """
        Ensure the project database exists, creating it if necessary.
        Uses the create_project_database function from the init script.
        """
        # Connect to the admin database
        admin_url = self.get_admin_database_url()
        engine = create_async_engine(admin_url, echo=False, poolclass=None)

        try:
            async with engine.begin() as conn:
                # Call the create_project_database function
                await conn.execute(
                    text("SELECT create_project_database(:project_name)"),
                    {"project_name": self.project_database_name}
                )
                logger.info(f"Ensured database exists for project: {self.project_database_name}")
        except Exception as e:
            logger.error(f"Error ensuring project database exists: {e}")
            raise
        finally:
            await engine.dispose()