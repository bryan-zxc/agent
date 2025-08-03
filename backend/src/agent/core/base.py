import logging
import uuid
from pathlib import Path
from typing import Union, List, Dict, Any
from PIL import Image
from ..services.llm_service import LLM
from ..utils.tools import encode_image, decode_image
from ..models.message_db import MessageDatabase, AgentType


# Set up logging
logger = logging.getLogger(__name__)


class BaseAgent:
    def __init__(self, id: str = None, agent_type: AgentType = None):
        # Use the class name as the caller for LLM usage tracking
        self.llm = LLM(caller=self.__class__.__name__)
        if id:
            self.id = id
        else:
            self.id = uuid.uuid4().hex

        self.agent_type = agent_type
        self._message_db = MessageDatabase()

        # Initialize messages property to use database
        self._messages_cache = None

    @property
    def messages(self) -> List[Dict[str, Any]]:
        """Get messages from database for this agent"""
        if self.agent_type is None:
            # Fallback to in-memory for agents without specified type
            if not hasattr(self, "_fallback_messages"):
                self._fallback_messages = []
            return self._fallback_messages

        return self._message_db.get_messages(self.agent_type, self.id)

    @messages.setter
    def messages(self, value: List[Dict[str, Any]]):
        """Set messages (for backward compatibility, though we prefer database storage)"""
        if self.agent_type is None:
            self._fallback_messages = value
        else:
            # Clear existing messages and add new ones
            self._message_db.clear_messages(self.agent_type, self.id)
            for msg in value:
                self._message_db.add_message(
                    self.agent_type, self.id, msg["role"], msg["content"]
                )

    def add_message(
        self,
        role: str,
        content: str,
        image: Union[str, Path, Image.Image] = None,
        verbose=True,
    ):
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

        if verbose:
            if isinstance(content, str):
                # print(content, flush=True)
                logger.info(content)
            elif isinstance(content, list):
                for c in content:
                    if c.get("type") == "text":
                        # print(c["text"], flush=True)
                        logger.info(c["text"])
                    else:
                        decode_image(
                            c["image_url"]["url"].replace("data:image/png;base64,", "")
                        ).show()

        if self.agent_type is None:
            # Fallback to in-memory storage
            if not hasattr(self, "_fallback_messages"):
                self._fallback_messages = []
            self._fallback_messages.append({"role": role, "content": content})
        else:
            # Store in database
            self._message_db.add_message(self.agent_type, self.id, role, content)
