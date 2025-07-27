import logging
import sys
from pathlib import Path
from typing import Union
from PIL import Image
from azureopenai.llm_service_async2 import AzureLLM
from agent.tools import encode_image, decode_image


# Set up logging
logger = logging.getLogger(__name__)
# logger.addHandler(logging.FileHandler("agent.log"))
# logger.setLevel(logging.DEBUG)


class BaseAgent:
    def __init__(self):
        self.llm = AzureLLM()

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

        if hasattr(self, "messages"):
            self.messages.append({"role": role, "content": content})
        else:
            self.messages = [{"role": role, "content": content}]
