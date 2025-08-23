"""Message Manager for efficient in-memory message handling with database synchronisation"""

from typing import Dict, List, Any, Optional, TYPE_CHECKING
import logging

if TYPE_CHECKING:
    from ..models.agent_database import AgentDatabase, AgentType

logger = logging.getLogger(__name__)


class MessageManager:
    """
    Manages messages for a specific agent with in-memory caching to reduce database queries.
    
    Provides efficient message operations by maintaining an in-memory message list that stays
    synchronised with the database, eliminating the need for repeated database queries and
    preventing stale message issues during LLM interactions.
    """
    
    def __init__(self, db: 'AgentDatabase', agent_type: 'AgentType', agent_id: str):
        """
        Initialise MessageManager for a specific agent.
        
        Args:
            db: AgentDatabase instance for persistence
            agent_type: Type of agent ("planner", "worker", or "router")
            agent_id: Unique identifier for the agent instance
        """
        self.db = db
        self.agent_type = agent_type
        self.agent_id = agent_id
        self._messages: List[Dict[str, Any]] = []
        self._synced = False  # Track if we've synced from database yet
        
        logger.debug(f"Initialised MessageManager for {agent_type} {agent_id} (will sync on first use)")
    
    async def add_message(self, role: str, content: Any) -> List[Dict[str, Any]]:
        """
        Add a message and return the updated complete message list.
        
        This method persists to database and updates the in-memory cache in one operation,
        ensuring consistency and eliminating the need for separate database queries.
        
        Args:
            role: Message role ('user', 'assistant', 'system', 'developer')
            content: Message content (can be string, list, or other JSON-serialisable content)
            
        Returns:
            Complete updated message list for immediate use with LLM calls
        """
        # Ensure we're synced with database first
        if not self._synced:
            await self._sync_from_db()
        
        # Persist to database
        message_id = await self.db.add_message(self.agent_type, self.agent_id, role, content)
        
        if message_id is not None:
            # Add to in-memory cache
            message_dict = {
                "role": role,
                "content": content
            }
            self._messages.append(message_dict)
            
            logger.debug(f"Added message (ID: {message_id}) to {self.agent_type} {self.agent_id}")
        else:
            logger.error(f"Failed to add message to database for {self.agent_type} {self.agent_id}")
            
        return await self.get_messages()
    
    async def get_messages(self) -> List[Dict[str, Any]]:
        """
        Get complete message list for LLM interactions.
        
        Returns a copy of the in-memory message list, avoiding database queries
        for read operations while maintaining immutability.
        
        Returns:
            Complete message list ready for LLM API calls
        """
        # Ensure we have the latest messages from database
        if not self._synced:
            await self._sync_from_db()
        return self._messages.copy()
    
    async def clear_messages(self) -> None:
        """
        Clear all messages for this agent from both database and memory.
        
        Use with caution as this permanently removes conversation history.
        """
        await self.db.clear_messages(self.agent_type, self.agent_id)
        self._messages.clear()
        self._synced = True  # We're now synced with the empty database state
        logger.info(f"Cleared all messages for {self.agent_type} {self.agent_id}")
    
    async def refresh_from_db(self) -> List[Dict[str, Any]]:
        """
        Force refresh from database to handle external changes.
        
        Normally not needed as MessageManager maintains consistency,
        but useful for debugging or handling concurrent modifications.
        
        Returns:
            Updated message list after database sync
        """
        await self._sync_from_db()
        return await self.get_messages()
    
    async def _sync_from_db(self) -> None:
        """Load messages from database into in-memory cache."""
        try:
            self._messages = await self.db.get_messages(self.agent_type, self.agent_id)
            self._synced = True
            logger.debug(f"Synced {len(self._messages)} messages from database for {self.agent_type} {self.agent_id}")
        except Exception as e:
            logger.error(f"Failed to sync messages from database for {self.agent_type} {self.agent_id}: {e}")
            self._messages = []
            self._synced = False  # Mark as not synced on failure
    
    def message_count(self) -> int:
        """Get current message count without database query."""
        return len(self._messages)
    
    def __len__(self) -> int:
        """Allow len() operation on MessageManager."""
        return self.message_count()
    
    def __repr__(self) -> str:
        return f"MessageManager({self.agent_type}:{self.agent_id}, {len(self._messages)} messages)"