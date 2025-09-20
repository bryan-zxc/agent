#!/usr/bin/env python3
"""
Database management CLI for PostgreSQL project databases.

This script provides command-line access to database operations,
leveraging the existing DatabaseConfig and SQL functions.

Architecture:
- SQL layer: create_project_database() function (creates empty DB)
- Library layer: DatabaseConfig (connection management)
- This script: Adds schema creation and CLI interface
"""

import asyncio
import sys
from pathlib import Path
import argparse
import logging
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.agent.database.connection import DatabaseConfig
from src.agent.models.agent_database import Base

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def create_project_with_schema(project_name: str, drop_if_exists: bool = False):
    """
    Create a project database with full SQLAlchemy schema.

    Steps:
    1. Use SQL function to create empty database
    2. Apply SQLAlchemy schema (tables, indexes, constraints)

    Args:
        project_name: Name of the project/database
        drop_if_exists: Whether to drop existing database first
    """
    # Create a config instance for the admin database
    config = DatabaseConfig()

    try:
        if drop_if_exists:
            await drop_project_database(project_name)
            logger.info(f"Dropped existing database '{project_name}'")

        # Step 1: Create empty database directly (SQL function can't work in transactions)
        admin_engine = create_async_engine(
            config.get_admin_database_url(),
            echo=False,
            isolation_level="AUTOCOMMIT"
        )

        try:
            async with admin_engine.connect() as conn:
                # Check if database exists
                result = await conn.execute(
                    text("SELECT 1 FROM pg_database WHERE datname = :dbname"),
                    {"dbname": project_name}
                )

                if not result.scalar():
                    # Create the database
                    await conn.execute(
                        text(f'CREATE DATABASE "{project_name}" WITH TEMPLATE = template0 '
                             f'ENCODING = \'UTF8\' LC_COLLATE = \'en_US.utf8\' LC_CTYPE = \'en_US.utf8\'')
                    )
                    logger.info(f"Created database '{project_name}'")
        finally:
            await admin_engine.dispose()

        # Step 2: Connect to new database and create schema
        project_url = config.get_database_url(database_name=project_name)
        project_engine = create_async_engine(project_url, echo=False)

        try:
            logger.info(f"Applying SQLAlchemy schema to '{project_name}'...")
            async with project_engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

            # Verify schema creation
            async with project_engine.connect() as conn:
                result = await conn.execute(
                    text("""
                        SELECT table_name
                        FROM information_schema.tables
                        WHERE table_schema = 'public'
                        ORDER BY table_name
                    """)
                )
                tables = [row[0] for row in result]

                if tables:
                    logger.info(f"Successfully created {len(tables)} tables:")
                    for table in tables:
                        logger.info(f"  - {table}")
                else:
                    logger.warning("No tables created - check your models")

        finally:
            await project_engine.dispose()

    except Exception as e:
        logger.error(f"Failed to create database '{project_name}': {e}")
        raise


async def drop_project_database(project_name: str):
    """
    Drop a project database if it exists.

    Args:
        project_name: Name of the database to drop
    """
    config = DatabaseConfig()
    admin_engine = create_async_engine(
        config.get_admin_database_url(),
        echo=False,
        isolation_level="AUTOCOMMIT"
    )

    try:
        async with admin_engine.connect() as conn:
            # First check if database exists
            result = await conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :dbname"),
                {"dbname": project_name}
            )

            if not result.scalar():
                logger.info(f"Database '{project_name}' does not exist")
                return

            # Terminate existing connections
            await conn.execute(
                text("""
                    SELECT pg_terminate_backend(pid)
                    FROM pg_stat_activity
                    WHERE datname = :dbname AND pid <> pg_backend_pid()
                """),
                {"dbname": project_name}
            )

            # Drop the database
            await conn.execute(text(f'DROP DATABASE "{project_name}"'))
            logger.info(f"Successfully dropped database '{project_name}'")

    except Exception as e:
        logger.error(f"Failed to drop database '{project_name}': {e}")
        raise
    finally:
        await admin_engine.dispose()


async def list_project_databases():
    """List all project databases with statistics."""
    config = DatabaseConfig()
    admin_engine = create_async_engine(config.get_admin_database_url(), echo=False)

    try:
        async with admin_engine.connect() as conn:
            # Get all non-system databases
            result = await conn.execute(
                text("""
                    SELECT
                        datname as name,
                        pg_size_pretty(pg_database_size(datname)) as size,
                        pg_database_size(datname) as size_bytes
                    FROM pg_database
                    WHERE datname NOT IN (
                        'postgres', 'template0', 'template1',
                        'template_agent', 'agent_main'
                    )
                    ORDER BY datname
                """)
            )
            databases = result.fetchall()

            if databases:
                logger.info("\nProject Databases:")
                logger.info("=" * 60)
                logger.info(f"{'Database':<30} {'Size':<15}")
                logger.info("-" * 60)

                total_size = 0
                for db_name, size, size_bytes in databases:
                    logger.info(f"{db_name:<30} {size:<15}")
                    total_size += size_bytes

                logger.info("-" * 60)
                logger.info(f"{'Total:':<30} {pg_size_pretty(total_size):<15}")
                logger.info(f"\nFound {len(databases)} project database(s)")
            else:
                logger.info("No project databases found")
                logger.info("Use 'create' command to create a new project database")

    finally:
        await admin_engine.dispose()


def pg_size_pretty(size_bytes: int) -> str:
    """Convert bytes to human-readable format (matches PostgreSQL's format)."""
    for unit in ['B', 'kB', 'MB', 'GB', 'TB']:
        if abs(size_bytes) < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Manage PostgreSQL project databases for the agent system",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s create myproject           # Create a new project database
  %(prog)s create myproject --drop    # Recreate project database
  %(prog)s drop myproject             # Drop a project database
  %(prog)s list                       # List all project databases
        """
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Create command
    create_parser = subparsers.add_parser(
        "create",
        help="Create a new project database with schema"
    )
    create_parser.add_argument(
        "project",
        help="Project name (will be used as database name)"
    )
    create_parser.add_argument(
        "--drop",
        action="store_true",
        help="Drop the database if it already exists"
    )

    # Drop command
    drop_parser = subparsers.add_parser(
        "drop",
        help="Drop an existing project database"
    )
    drop_parser.add_argument(
        "project",
        help="Project name (database name)"
    )

    # List command
    list_parser = subparsers.add_parser(
        "list",
        help="List all project databases"
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    try:
        if args.command == "create":
            asyncio.run(create_project_with_schema(args.project, args.drop))
        elif args.command == "drop":
            asyncio.run(drop_project_database(args.project))
        elif args.command == "list":
            asyncio.run(list_project_databases())
    except KeyboardInterrupt:
        logger.info("\nOperation cancelled by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Operation failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()