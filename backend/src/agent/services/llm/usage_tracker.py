"""Async database operations for LLM usage tracking."""

import asyncio
import threading
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from ...models.agent_database import LLMUsage
from ...config.settings import settings
from .base import RequestType

logger = logging.getLogger(__name__)

# Create async engine and session factory for usage tracking
_engine = None
_async_session = None

def get_async_session():
    """Get or create async session factory for usage tracking."""
    global _engine, _async_session

    if _async_session is None:
        # Import here to avoid circular dependency
        from ...database.connection import DatabaseConfig

        db_config = DatabaseConfig()
        database_url = db_config.get_database_url()
        _engine = create_async_engine(
            database_url,
            echo=False
        )
        _async_session = async_sessionmaker(
            bind=_engine,
            class_=AsyncSession,
            expire_on_commit=False
        )

    return _async_session()


class UsageTracker:
    """Handles LLM usage tracking with async database operations."""
    
    def __init__(self, caller: str = "general"):
        """
        Initialise the usage tracker.
        
        Args:
            caller: Identifier for tracking usage by caller
        """
        self.caller = caller
    
    async def track_usage(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cost: float,
        request_type: RequestType,
    ) -> None:
        """
        Track LLM usage to the database asynchronously.
        
        Args:
            model: Model identifier used
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens
            cost: Calculated cost in USD
            request_type: Type of request (text, tools, structured, etc.)
        """
        try:
            async with get_async_session() as session:
                # Import here to avoid circular dependency
                from ...models.agent_database import LLMUsage
                
                usage_record = LLMUsage(
                    model=model,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cost=cost,
                    request_type=request_type.value,
                    caller=self.caller,
                    timestamp=datetime.now(timezone.utc),
                )
                
                session.add(usage_record)
                await session.commit()
                
                logger.info(
                    f"LLM Usage: {model}, Input: {input_tokens}, "
                    f"Output: {output_tokens}, Cost: ${cost:.6f}, "
                    f"Type: {request_type.value}, Caller: {self.caller}"
                )
                
        except Exception as e:
            logger.error(f"Failed to track usage: {e}")
    
    def track_usage_sync(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cost: float,
        request_type: RequestType,
    ) -> None:
        """
        Fire-and-forget async tracking from sync context.
        
        Args:
            model: Model identifier used
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens
            cost: Calculated cost in USD
            request_type: Type of request (text, tools, structured, etc.)
        """
        def handle_error(task):
            """Handle errors from async task."""
            if task.exception():
                logger.error(f"Usage tracking failed: {task.exception()}")
        
        try:
            # Try to get running event loop (async context like FastAPI)
            loop = asyncio.get_running_loop()
            task = loop.create_task(
                self.track_usage(model, input_tokens, output_tokens, cost, request_type)
            )
            task.add_done_callback(handle_error)
        except RuntimeError:
            # No event loop running - use daemon thread (pure sync context)
            def run_async():
                """Run async tracking in new event loop."""
                asyncio.run(
                    self.track_usage(model, input_tokens, output_tokens, cost, request_type)
                )
            
            thread = threading.Thread(target=run_async, daemon=True)
            thread.start()
    
    async def get_usage_stats(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        caller_filter: Optional[str] = None,
        model_filter: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get usage statistics from the database.
        
        Args:
            start_date: Start date for filtering (default: 30 days ago)
            end_date: End date for filtering (default: now)
            caller_filter: Filter by specific caller
            model_filter: Filter by specific model
            
        Returns:
            Dictionary containing usage statistics
        """
        try:
            async with get_async_session() as session:
                from ...models.agent_database import LLMUsage
                
                # Default date range
                if not end_date:
                    end_date = datetime.now(timezone.utc)
                if not start_date:
                    start_date = end_date - timedelta(days=30)
                
                # Build query
                query = select(
                    func.count(LLMUsage.id).label("total_requests"),
                    func.sum(LLMUsage.input_tokens).label("total_input_tokens"),
                    func.sum(LLMUsage.output_tokens).label("total_output_tokens"),
                    func.sum(LLMUsage.cost).label("total_cost"),
                    func.avg(LLMUsage.cost).label("avg_cost_per_request"),
                ).where(
                    and_(
                        LLMUsage.timestamp >= start_date,
                        LLMUsage.timestamp <= end_date,
                    )
                )
                
                # Apply filters
                if caller_filter:
                    query = query.where(LLMUsage.caller == caller_filter)
                if model_filter:
                    query = query.where(LLMUsage.model == model_filter)
                
                result = await session.execute(query)
                stats = result.first()
                
                # Get breakdown by model
                model_query = select(
                    LLMUsage.model,
                    func.count(LLMUsage.id).label("requests"),
                    func.sum(LLMUsage.cost).label("cost"),
                ).where(
                    and_(
                        LLMUsage.timestamp >= start_date,
                        LLMUsage.timestamp <= end_date,
                    )
                ).group_by(LLMUsage.model)
                
                if caller_filter:
                    model_query = model_query.where(LLMUsage.caller == caller_filter)
                
                model_result = await session.execute(model_query)
                model_breakdown = [
                    {"model": row.model, "requests": row.requests, "cost": float(row.cost)}
                    for row in model_result
                ]
                
                # Get breakdown by request type
                type_query = select(
                    LLMUsage.request_type,
                    func.count(LLMUsage.id).label("requests"),
                    func.sum(LLMUsage.cost).label("cost"),
                ).where(
                    and_(
                        LLMUsage.timestamp >= start_date,
                        LLMUsage.timestamp <= end_date,
                    )
                ).group_by(LLMUsage.request_type)
                
                if caller_filter:
                    type_query = type_query.where(LLMUsage.caller == caller_filter)
                if model_filter:
                    type_query = type_query.where(LLMUsage.model == model_filter)
                
                type_result = await session.execute(type_query)
                type_breakdown = [
                    {"type": row.request_type, "requests": row.requests, "cost": float(row.cost)}
                    for row in type_result
                ]
                
                return {
                    "period": {
                        "start": start_date.isoformat(),
                        "end": end_date.isoformat(),
                    },
                    "filters": {
                        "caller": caller_filter,
                        "model": model_filter,
                    },
                    "totals": {
                        "requests": stats.total_requests or 0,
                        "input_tokens": stats.total_input_tokens or 0,
                        "output_tokens": stats.total_output_tokens or 0,
                        "cost": float(stats.total_cost or 0),
                        "avg_cost_per_request": float(stats.avg_cost_per_request or 0),
                    },
                    "breakdown": {
                        "by_model": model_breakdown,
                        "by_type": type_breakdown,
                    }
                }
                
        except Exception as e:
            logger.error(f"Failed to get usage stats: {e}")
            return {
                "error": str(e),
                "period": {
                    "start": start_date.isoformat() if start_date else None,
                    "end": end_date.isoformat() if end_date else None,
                },
                "totals": {
                    "requests": 0,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "cost": 0.0,
                    "avg_cost_per_request": 0.0,
                },
                "breakdown": {
                    "by_model": [],
                    "by_type": [],
                }
            }
    
    async def get_caller_usage(
        self,
        limit: int = 10,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get usage breakdown by caller.
        
        Args:
            limit: Maximum number of callers to return
            start_date: Start date for filtering
            end_date: End date for filtering
            
        Returns:
            List of caller usage statistics
        """
        try:
            async with get_async_session() as session:
                from ...models.agent_database import LLMUsage
                
                # Default date range
                if not end_date:
                    end_date = datetime.now(timezone.utc)
                if not start_date:
                    start_date = end_date - timedelta(days=30)
                
                query = select(
                    LLMUsage.caller,
                    func.count(LLMUsage.id).label("requests"),
                    func.sum(LLMUsage.cost).label("total_cost"),
                    func.sum(LLMUsage.input_tokens).label("input_tokens"),
                    func.sum(LLMUsage.output_tokens).label("output_tokens"),
                ).where(
                    and_(
                        LLMUsage.timestamp >= start_date,
                        LLMUsage.timestamp <= end_date,
                    )
                ).group_by(
                    LLMUsage.caller
                ).order_by(
                    func.sum(LLMUsage.cost).desc()
                ).limit(limit)
                
                result = await session.execute(query)
                
                return [
                    {
                        "caller": row.caller,
                        "requests": row.requests,
                        "total_cost": float(row.total_cost),
                        "input_tokens": row.input_tokens,
                        "output_tokens": row.output_tokens,
                    }
                    for row in result
                ]
                
        except Exception as e:
            logger.error(f"Failed to get caller usage: {e}")
            return []