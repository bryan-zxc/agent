"""
Pytest configuration and fixtures for the test suite.

This file contains session-level fixtures that run automatically,
including cost reporting for LLM API usage during tests.
"""

import pytest
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
import sys

# Add backend src to path
backend_root = Path(__file__).parent.parent
sys.path.insert(0, str(backend_root / "src"))

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from agent.models.agent_database import LLMUsage
from agent.config.settings import settings

logger = logging.getLogger(__name__)


@pytest.fixture(scope="session", autouse=True)
def test_cost_report():
    """
    Session fixture that reports LLM API costs after all tests complete.
    
    This fixture runs automatically at the end of the test session and
    generates a comprehensive cost report for the current test run.
    """
    # Setup happens before tests
    start_time = datetime.now(timezone.utc)
    yield  # Tests run here
    
    # Teardown: Generate cost report after all tests
    asyncio.run(_generate_cost_report(start_time))


async def _generate_cost_report(start_time: datetime):
    """
    Generate and print a cost report for the test session.
    
    Args:
        start_time: When the test session started
    """
    # Create database session
    database_url = f"sqlite+aiosqlite:///{settings.database_path}"
    engine = create_async_engine(
        database_url,
        echo=False,
        connect_args={"check_same_thread": False}
    )
    
    async_session = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False
    )
    
    async with async_session() as session:
        # Query total costs for this test run
        result = await session.execute(
            select(
                func.count(LLMUsage.id).label("total_requests"),
                func.sum(LLMUsage.cost).label("total_cost"),
                func.sum(LLMUsage.input_tokens).label("total_input"),
                func.sum(LLMUsage.output_tokens).label("total_output")
            ).where(
                and_(
                    LLMUsage.caller.like("test%"),
                    LLMUsage.timestamp >= start_time
                )
            )
        )
        
        totals = result.one()
        
        # Only print report if there were API calls
        if totals.total_requests and totals.total_requests > 0:
            print("\n" + "=" * 70)
            print("LLM API COST REPORT - CURRENT TEST RUN")
            print("=" * 70)
            print(f"Session Duration: {datetime.now(timezone.utc) - start_time}")
            print(f"Total API Calls: {totals.total_requests}")
            print(f"Total Cost: ${totals.total_cost:.6f}")
            print(f"Input Tokens: {totals.total_input:,}")
            print(f"Output Tokens: {totals.total_output:,}")
            print(f"Total Tokens: {totals.total_input + totals.total_output:,}")
            print("-" * 70)
            
            # Breakdown by model (since we don't have provider column)
            provider_result = await session.execute(
                select(
                    LLMUsage.model,
                    func.count(LLMUsage.id).label("requests"),
                    func.sum(LLMUsage.cost).label("cost"),
                    func.sum(LLMUsage.input_tokens).label("input_tokens"),
                    func.sum(LLMUsage.output_tokens).label("output_tokens")
                ).where(
                    and_(
                        LLMUsage.caller.like("test%"),
                        LLMUsage.timestamp >= start_time
                    )
                ).group_by(LLMUsage.model)
            )
            
            print("\nCost by Model:")
            for row in provider_result.all():
                tokens_total = row.input_tokens + row.output_tokens
                print(f"  {row.model}:")
                print(f"    Requests: {row.requests}")
                print(f"    Cost: ${row.cost:.6f}")
                print(f"    Tokens: {tokens_total:,} (in: {row.input_tokens:,}, out: {row.output_tokens:,})")
            
            # Breakdown by request type
            type_result = await session.execute(
                select(
                    LLMUsage.request_type,
                    func.count(LLMUsage.id).label("requests"),
                    func.sum(LLMUsage.cost).label("cost")
                ).where(
                    and_(
                        LLMUsage.caller.like("test%"),
                        LLMUsage.timestamp >= start_time
                    )
                ).group_by(LLMUsage.request_type)
            )
            
            type_breakdown = type_result.all()
            if type_breakdown:
                print("\nCost by Request Type:")
                for row in type_breakdown:
                    print(f"  {row.request_type}: {row.requests} requests, ${row.cost:.6f}")
            
            print("=" * 70)
            print()
    
    await engine.dispose()


@pytest.fixture
async def verify_cost_tracking():
    """
    Fixture to help tests verify that cost tracking is working.
    
    Returns a function that checks if usage was tracked for a given caller.
    Tests can use this to verify tracking without making extra API calls.
    """
    database_url = f"sqlite+aiosqlite:///{settings.database_path}"
    engine = create_async_engine(
        database_url,
        echo=False,
        connect_args={"check_same_thread": False}
    )
    
    async_session = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False
    )
    
    async def check_tracking(caller: str, min_count: int = 1) -> bool:
        """
        Check if cost tracking recorded usage for a caller.
        
        Args:
            caller: The caller identifier to check
            min_count: Minimum number of records expected
            
        Returns:
            True if tracking is working
        """
        async with async_session() as session:
            result = await session.execute(
                select(func.count(LLMUsage.id)).where(
                    LLMUsage.caller == caller
                )
            )
            count = result.scalar() or 0
            return count >= min_count
    
    yield check_tracking
    
    await engine.dispose()