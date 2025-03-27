from datetime import datetime
from enum import Enum
import json
import os

from src.util import Logger

from google import genai
from google.genai.types import GenerateContentConfig

API_KEY = os.getenv("AI_PLATFORM_API_KEY")
LLM_MODEL = os.getenv("LLM_MODEL")


class InitialIntentTypes(Enum):
    UNKNOWN = 0
    REGISTER_BILL = 1
    SUM_BILLS = 2
    REGISTER_CATEGORY = 3
    DELETE_BILL = 4
    LIST_CATEGORIES = 5


INITIAL_INTENT_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "intent": {"type": "INTEGER"},
    },
}

INITIAL_INTENT_SYSTEM_PROMPT = f"""
    You are an assistant that helps discover the intent of a message.
    These are the possible content of the message and what should be returned:
        1. Data about a purchase. 'intent'={InitialIntentTypes.REGISTER_BILL.value}
        2. Question about expenses in a specific period. 'intent'={InitialIntentTypes.SUM_BILLS.value}
        3. Name of an expense category. 'intent'={InitialIntentTypes.REGISTER_CATEGORY.value}
        4. Request to delete a bill. 'intent'={InitialIntentTypes.DELETE_BILL.value}.
        5. Request to list categories. 'intent'={InitialIntentTypes.LIST_CATEGORIES.value}.
    If the user's request does not fit into these options, intent_type={InitialIntentTypes.UNKNOWN.value}.
    """

REGISTER_BILL_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "category_id": {"type": "INTEGER"},
        "value": {"type": "NUMBER"},
        "date": {"type": "STRING"},
    },
    "required": ["category_id", "value", "date"],
}

REGISTER_BILL_SYSTEM_PROMPT = """
    The user wants to register a new bill.
    For the examples, consider the current date to be '2025-03-16' and the categories
    [{{'id': 1, 'name': 'food'}}, {{'id': 2, 'name': 'grocery'}}, {{'id': 3, 'name': 'default'}}]
    Examples:
        'I spent 20.30 on a snack'. value=20.30, category_id=1, date='2025-03-16'
        'I bought a hat for 50 reais yesterday'. value=50.00, category_id=2, date='2025-03-15'
        'I bought a doll on Tuesday for 10 reais'. value=10.00, category_id=3, date='2025-03-16'
        'I spent 10 reais on cookies this month'. value=10.00, category_id=1, date='2025-03-01'
    The possible categories for this user are: {categories}
    Today is {today}
    """  # TODO improve this prompt

READ_BILLS_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "category_id": {"type": "INTEGER"},
        "from": {"type": "STRING"},
        "until": {"type": "STRING"},
    },
    "required": ["category_id", "from", "until"],
}

READ_BILLS_SYSTEM_PROMPT = """
    The user want to search for bills.
    For the examples, consider the current date to be '2025-03-16'
    Examples:
        'How much did I spend on food this month?': category_id=1, from='2025-03-01', until='2025-04-01'
        'What was my grocery consumption last month?': category_id=2, from='2025-02-01', until='2025-03-01'
        'How much did I spend in October?': category_id=null, from='2024-10-01', until='2024-11-01'
        'How much did I spend this week on miscellaneous?': category_id=3, from='2025-03-10', until='2025-03-17'
    The possible categories for this user are: {categories}
    Today is {today}
    """

REGISTER_CATEGORY_SCHEMA = {
    "type": "OBJECT",
    "properties": {"name": {"type": "STRING"}, "description": {"type": "STRING"}},
    "required": ["name", "description"],
}

REGISTER_CATEGORY_SYSTEM_PROMPT = """
    The user is trying to register a new category.
    Examples:
        'Create an expense category called grocery shopping'. name='grocery shopping', description='Expenses related to grocery shopping'
        'I'm going to create an expense category called entertainment'. name='entertainment', description='Expenses related to entertainment'
    """


def get_config(response_schema):
    return GenerateContentConfig(
        temperature=0,
        max_output_tokens=100,
        response_mime_type="application/json",
        response_schema=response_schema,
    )


client = genai.Client(api_key=API_KEY)


async def get_user_intent(user_prompt):
    system_prompt = INITIAL_INTENT_SYSTEM_PROMPT

    intent_value, tokens = await generate_content(
        [system_prompt, user_prompt], INITIAL_INTENT_SCHEMA
    )

    return InitialIntentTypes(intent_value["intent"]), tokens


async def get_bill_to_register(user_prompt, categories):
    system_prompt = REGISTER_BILL_SYSTEM_PROMPT.format(
        categories=categories, today=datetime.now().strftime("%Y-%m-%d")
    )

    return await generate_content([system_prompt, user_prompt], REGISTER_BILL_SCHEMA)


async def get_bills_to_sum_query_data(user_prompt, categories):
    system_prompt = READ_BILLS_SYSTEM_PROMPT.format(
        categories=categories, today=datetime.now().strftime("%Y-%m-%d")
    )

    return await generate_content([system_prompt, user_prompt], READ_BILLS_SCHEMA)


async def get_category_to_register(user_prompt):
    return await generate_content(
        [REGISTER_CATEGORY_SYSTEM_PROMPT, user_prompt], REGISTER_CATEGORY_SCHEMA
    )


async def generate_content(contents, schema):
    response = await client.aio.models.generate_content(
        model=LLM_MODEL,
        contents=contents,
        config=get_config(schema),
    )
    logger = Logger()
    logger.info(response.text)

    return json.loads(response.text), response.usage_metadata.total_token_count
