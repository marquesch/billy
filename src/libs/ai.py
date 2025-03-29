from datetime import datetime
from enum import Enum
import json
import os

from src.util import Logger

from google import genai
from google.genai.types import GenerateContentConfig
from httpx import ConnectError

REQUEST_RETRIES = 3

API_KEY = os.getenv("AI_PLATFORM_API_KEY")
LLM_MODEL = os.getenv("LLM_MODEL")


class InitialIntentTypes(Enum):
    UNKNOWN = "unknown"
    REGISTER_BILL = "reg_bill"
    SUM_BILLS = "sum_bills"
    REGISTER_CATEGORY = "reg_category"
    DELETE_BILL = "del_bill"
    LIST_CATEGORIES = "list_categories"
    REGISTER_FAKE_BILLS = "reg_fake_bill"
    DELETE_FAKE_BILLS = "del_fake_bill"
    ANALYZE_EXPENSE_TREND = "analyze_expense_trend"


def get_config(max_tokens, response_schema=None):
    response_mime_type = (
        "application/json" if response_schema is not None else "text/plain"
    )
    return GenerateContentConfig(
        temperature=0,
        max_output_tokens=max_tokens,
        response_mime_type=response_mime_type,
        response_schema=response_schema,
    )


client = genai.Client(api_key=API_KEY)


def get_prompt(key, **kwargs):
    import time

    st = time.perf_counter()
    with open("src/libs/ai.json", "r") as f:
        data = json.load(f)
    logger = Logger()
    end = time.perf_counter()
    logger.info(f"Loaded ai.json in {(end - st) * 1000} ms")
    return data["system_prompt"][key].format(**kwargs)


def get_schema(key):
    with open("src/libs/ai.json", "r") as f:
        data = json.load(f)
    return data["schema"][key]


async def get_user_intent(user_prompt):
    system_prompt = get_prompt("INITIAL_INTENT")
    schema = get_schema("INITIAL_INTENT")

    intent_value, tokens = await generate_content([system_prompt, user_prompt], schema)

    return InitialIntentTypes(intent_value["intent"]), tokens


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

    intent, tokens = await generate_content([system_prompt, user_prompt], schema)

    return intent["value"], tokens


async def get_analyze_expense_trend(categories, bills):
    system_prompt = get_prompt(
        "ANALYZE_EXPENSE_TREND", categories=categories, bills=bills
    )

    return await generate_content(system_prompt, max_tokens=200)


async def generate_content(contents, schema=None, max_tokens=100):
    logger = Logger()

    for i in range(REQUEST_RETRIES):
        try:
            response = await client.aio.models.generate_content(
                model=LLM_MODEL,
                contents=contents,
                config=get_config(max_tokens, schema),
            )

            break
        except ConnectError as e:
            logger.error(e)
            if i == REQUEST_RETRIES - 1:
                raise

    logger.info(response.text)

    if schema is not None:
        resp = json.loads(response.text)
    else:
        resp = response.text

    return resp, response.usage_metadata.total_token_count
