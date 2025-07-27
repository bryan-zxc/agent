import os
import random
import time
import json
import re
from pydantic import BaseModel, ValidationError
from datetime import datetime, timedelta, timezone
from openai import OpenAI


MAX_LLM_RETRIES = 3


def delay_exp(e, x):
    """
    Delay function to handle exceptions with exponential backoff.
    """
    delay_secs = 5 * (x + 1)
    randomness_collision_avoidance = random.randint(0, 1000) / 1000.0
    sleep_dur = delay_secs + randomness_collision_avoidance
    print(f"Retrying in {round(sleep_dur,2)} seconds due to: {e}", flush=True)
    time.sleep(sleep_dur)


class OpenAILLM:
    def __init__(self):
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    async def a_get_response(
        self,
        messages: list[dict],
        model: str = "gpt-4.1",
        temperature: float = 0,
        response_format: BaseModel = None,
        tools: list = None,
    ):
        return self.get_response(messages, model, temperature, response_format, tools)

    def get_response(
        self,
        messages: list[dict],
        model: str = "gpt-4.1",
        temperature: float = 0,
        response_format: BaseModel | dict = None,
        tools: list = None,
    ):
        for x in range(MAX_LLM_RETRIES):
            try:
                if tools:
                    return self._get_response_tools(messages, model, temperature, tools)
                if response_format:
                    return self._get_response_structured(
                        messages, model, temperature, response_format
                    )
                return self._get_response_text_only(messages, model, temperature)
            except ValidationError as e:
                print(f"Validation error: {e}", flush=True)
                delay_exp(e, x)
            except Exception as e:
                print(f"Error: {e}", flush=True)
                delay_exp(e, x)

    def _get_response_text_only(self, messages, model, temperature):
        response = self.client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
        )
        return response.choices[0].message

    def _get_response_tools(self, messages, model, temperature, tools):
        response = self.client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            tools=tools,
        )
        return response.choices[0].message

    def _get_response_structured(
        self, messages, model, temperature, response_format
    ) -> BaseModel | str:
        if issubclass(response_format, BaseModel):
            response = self.client.beta.chat.completions.parse(
                messages=messages,
                model=model,
                temperature=temperature,
                response_format=response_format,
            )
            return response.choices[0].message.parsed
        elif response_format == {"type": "json_object"}:
            error_msg = []
            for _ in range(2):
                response = self.client.chat.completions.create(
                    model=model,
                    messages=messages + error_msg,
                    temperature=temperature,
                    response_format=response_format,
                )
                json_str = response.choices[0].message.content
                try:
                    json.loads(json_str)
                    return json_str
                except:
                    json_str = re.sub(r"[\x00-\x1F]+", "", json_str)
                try:
                    json.loads(json_str)
                    return json_str
                except Exception as e:
                    error_msg.append(
                        {
                            "role": "system",
                            "content": f"The JSON returned is:\n{json_str}\n\nIt cannot be converted by json.loads with the following error:\n{e}\n\nGenerate a new JSON without the error.",
                        }
                    )
        else:
            # This is not expected, just leaving it in case there are acceptable values I'm not aware of.
            logging.warning(
                "Unknown response_format input, expected BaseModel or {'type': 'json_object'} and got %s",
                response_format,
            )
            response = self.client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                response_format=response_format,
            )
            return response.choices[0].message.content
