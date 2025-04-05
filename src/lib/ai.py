from datetime import datetime
import json
import os

from google import genai
from google.genai.types import GenerateContentConfig
from httpx import ConnectError

REQUEST_RETRIES = 3

API_KEY = os.getenv("AI_PLATFORM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "")
PROMPTS_FILE_PATH = "data/ai.json"


def get_config(max_tokens, response_schema=None, temperature=0.0):
    response_mime_type = (
        "application/json" if response_schema is not None else "text/plain"
    )
    return GenerateContentConfig(
        temperature=temperature,
        max_output_tokens=max_tokens,
        response_mime_type=response_mime_type,
        response_schema=response_schema,
    )


client = genai.Client(api_key=API_KEY)


def get_prompt(key, **kwargs):
    with open(PROMPTS_FILE_PATH, "r") as f:
        data = json.load(f)
    return data["system_prompt"][key].format(**kwargs)


def get_schema(key):
    with open(PROMPTS_FILE_PATH, "r") as f:
        data = json.load(f)
    return data["schema"][key]


async def get_user_intent(user_prompt, system_prompt=None):
    if system_prompt is None:
        system_prompt = get_prompt("INITIAL_INTENT")

    schema = get_schema("INITIAL_INTENT")

    tokens, intent_value = await generate_content([system_prompt, user_prompt], schema)

    return tokens, intent_value["intent"]


async def get_bill_to_register(user_prompt, categories):
    today = datetime.now().strftime("%Y-%m-%d")
    system_prompt = get_prompt("REGISTER_BILL", categories=categories, today=today)
    schema = get_schema("REGISTER_BILL")

    return await generate_content([system_prompt, user_prompt], schema)


async def get_bills_query_data(user_prompt, categories):
    today = datetime.now().strftime("%Y-%m-%d")
    system_prompt = get_prompt("READ_BILLS", categories=categories, today=today)
    schema = get_schema("READ_BILLS")

    return await generate_content([system_prompt, user_prompt], schema)


async def get_category_to_register(user_prompt):
    system_prompt = get_prompt("REGISTER_CATEGORY")
    schema = get_schema("REGISTER_CATEGORY")

    return await generate_content([system_prompt, user_prompt], schema)


async def get_yes_or_no_answer(user_prompt):
    system_prompt = get_prompt("YES_OR_NO")
    schema = get_schema("YES_OR_NO")

    tokens, intent = await generate_content([system_prompt, user_prompt], schema)

    return tokens, intent["value"]


async def get_expenses_analysis(categories, bills):
    system_prompt = get_prompt(
        "ANALYZE_EXPENSE_TREND", categories=categories, bills=bills
    )

    return await generate_content(system_prompt, max_tokens=300, temperature=0.7)


async def get_courtesy_answer(user_prompt):
    system_prompt = get_prompt("COURTESY_ANSWER")

    tokens, answer = await generate_content(
        [system_prompt, user_prompt], temperature=0.7
    )

    return tokens, answer


async def generate_content(contents, schema=None, max_tokens=100, temperature=0.0):
    for _ in range(REQUEST_RETRIES):
        try:
            response = await client.aio.models.generate_content(
                model=LLM_MODEL,
                contents=contents,
                config=get_config(max_tokens, schema, temperature),
            )

            if schema is not None:
                resp = json.loads(response.text)
            else:
                resp = response.text

            return response.usage_metadata.total_token_count, resp

        except ConnectError:
            continue

    raise ConnectError
