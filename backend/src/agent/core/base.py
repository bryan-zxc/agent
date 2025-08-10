import logging
import uuid
from pathlib import Path
from typing import Union, List, Dict, Any, Optional
from PIL import Image
from datetime import datetime, timezone
from ..services.llm_service import LLM
from ..utils.tools import encode_image, decode_image
from ..models.agent_database import AgentDatabase, AgentType, Router, Planner, Worker


# Set up logging
logger = logging.getLogger(__name__)


class BaseAgent:
    def __init__(self, id: str = None, agent_type: AgentType = None):
        # Use the class name as the caller for LLM usage tracking
        self.llm = LLM(caller=self.__class__.__name__)

        if id:
            self.id = id
            self._init_by_id = True
        else:
            self.id = uuid.uuid4().hex
            self._init_by_id = False

        self.agent_type = agent_type
        self._agent_db = AgentDatabase()

        # Initialize messages property to use database
        self._messages_cache = None

    # Common agent properties with database sync

    @property
    def model(self):
        return getattr(self, "_model", None)

    @model.setter
    def model(self, value):
        self._model = value
        self.update_agent_state(model=value)

    @property
    def temperature(self):
        return getattr(self, "_temperature", None)

    @temperature.setter
    def temperature(self, value):
        self._temperature = value
        self.update_agent_state(temperature=value)

    @property
    def messages(self) -> List[Dict[str, Any]]:
        """Get messages from database for this agent"""
        if self.agent_type is None:
            # Fallback to in-memory for agents without specified type
            if not hasattr(self, "_fallback_messages"):
                self._fallback_messages = []
            return self._fallback_messages

        return self._agent_db.get_messages(self.agent_type, self.id)

    @messages.setter
    def messages(self, value: List[Dict[str, Any]]):
        """Set messages (for backward compatibility, though we prefer database storage)"""
        if self.agent_type is None:
            self._fallback_messages = value
        else:
            # Clear existing messages and add new ones
            self._agent_db.clear_messages(self.agent_type, self.id)
            for msg in value:
                self._agent_db.add_message(
                    self.agent_type, self.id, msg["role"], msg["content"]
                )

    def add_message(
        self,
        role: str,
        content: str,
        image: Union[str, Path, Image.Image] = None,
        verbose=True,
    ) -> Optional[int]:
        """
        Adds a message to the conversation history.

        :param role: The role of the message sender (e.g., 'user', 'assistant').
        :param content: The content of the message.
        :return: A list of messages including the new message.
        """
        if image:
            if content:
                if isinstance(content, str):
                    content = [
                        {"type": "text", "text": content},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{encode_image(image)}"
                            },
                        },
                    ]
                else:
                    content.append(
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{encode_image(image)}"
                            },
                        }
                    )
            else:
                content = [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{encode_image(image)}"
                        },
                    }
                ]

        if isinstance(content, str):
            if verbose:
                logger.info(content)
            else:
                logger.debug(content)
        elif isinstance(content, list):
            for c in content:
                if c.get("type") == "text":
                    if verbose:
                        logger.info(c["text"])
                    else:
                        logger.debug(c["text"])
                else:
                    if verbose:
                        decode_image(
                            c["image_url"]["url"].replace("data:image/png;base64,", "")
                        ).show()

        if self.agent_type is None:
            # Fallback to in-memory storage
            if not hasattr(self, "_fallback_messages"):
                self._fallback_messages = []
            self._fallback_messages.append({"role": role, "content": content})
            return None  # In-memory storage doesn't have IDs
        else:
            # Store in database and return message ID
            return self._agent_db.add_message(self.agent_type, self.id, role, content)

    # Agent State Management

    def update_agent_state(self, **kwargs):
        """Update any agent state fields dynamically"""
        if not kwargs or not self.agent_type:
            return

        # Always update the updated_at timestamp
        kwargs["updated_at"] = datetime.now(timezone.utc)

        # Build dynamic update query
        with self._agent_db.SessionLocal() as session:
            # Get the appropriate model class and ID field
            model_mapping = {
                "router": (Router, "router_id"),
                "planner": (Planner, "planner_id"),
                "worker": (Worker, "worker_id"),
            }

            if self.agent_type not in model_mapping:
                return

            model_class, id_field = model_mapping[self.agent_type]

            # Get the existing record
            record = (
                session.query(model_class)
                .filter(getattr(model_class, id_field) == self.id)
                .first()
            )

            if record:
                # Update all provided fields
                for field, value in kwargs.items():
                    if hasattr(record, field):
                        setattr(record, field, value)

                session.commit()
