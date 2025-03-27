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
    REGISTER_FAKE_BILLS = 6
    DELETE_FAKE_BILLS = 7
    ANALYZE_EXPENSE_TREND = 8


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
        6. Request to register fake bills. 'intent'={InitialIntentTypes.REGISTER_FAKE_BILLS.value}.
        7. Request to delete fake bills. 'intent'={InitialIntentTypes.DELETE_FAKE_BILLS.value}.
        8. Request to analyze expenses. 'intent'={InitialIntentTypes.ANALYZE_EXPENSE_TREND.value}.
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
    Given his categories: {categories}
    And that today is {today}
    The expected values are as follows:
        category_id: the id of the category that the bill most fits into.
        value: the value of the bill.
        date: the date of the bill. Consider his input relative to the current date.
    """

READ_BILLS_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "category_id": {"type": "INTEGER"},
        "range": {"type": "ARRAY", "items": {"type": "STRING"}},
        "show_bills": {"type": "BOOLEAN"},
    },
    "required": ["range", "show_bills"],
}

READ_BILLS_SYSTEM_PROMPT = """
    The user want to search for bills.
    Given his categories: {categories}
    And that today is {today}
    The expected values are as follows:
        category_id: the id of the category he might be interested in. remove this key if he doesn't want to filter by category.
        show_bills: true if he explicitly says he wants to see the details the bills. false otherwise.
            Examples: 'How much did I spend on food this month?' show_bills=false
                'How much did I spend on food this month? Also show me the bills' show_bills=true
        range: the range of the period he wants to search for. if he wants to search for a specific date, then the range has only the mentioned date.
        if he wants to search for a period, then the range has the start and end date.
    """

REGISTER_CATEGORY_SCHEMA = {
    "type": "OBJECT",
    "properties": {"name": {"type": "STRING"}, "description": {"type": "STRING"}},
    "required": ["name", "description"],
}

REGISTER_CATEGORY_SYSTEM_PROMPT = """
    The user is trying to register a new category.
    The expected values are as follows:
        name: the name of the category.
        description: the description of the category. null if the user doesn't mention a description.
    """

YES_OR_NO_SCHEMA = {
    "type": "OBJECT",
    "properties": {"value": {"type": "BOOLEAN"}},
    "required": ["value"],
}

YES_OR_NO_SYSTEM_PROMPT = """
    The user is answearing a yes or on question.
    If his answer is afirmative, value=true.
    If his answer is negative, value=false.
    """

ANALYZE_EXPENSE_TREND_PROMPT = """
    The user wants you to analyze his expenses.
    I need you to summarize his expenses in last than 500 words.
    Explain where he spends the most money and how much.
    And suggest where he could save money.
    For the analysis, consider his categories to be:
    {categories}
    His expenses data are:
    {bills}
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


async def get_bills_query_data(user_prompt, categories):
    system_prompt = READ_BILLS_SYSTEM_PROMPT.format(
        categories=categories, today=datetime.now().strftime("%Y-%m-%d")
    )

    return await generate_content([system_prompt, user_prompt], READ_BILLS_SCHEMA)


async def get_category_to_register(user_prompt):
    return await generate_content(
        [REGISTER_CATEGORY_SYSTEM_PROMPT, user_prompt], REGISTER_CATEGORY_SCHEMA
    )


async def get_yes_or_no_answer(user_prompt):
    intent, tokens = await generate_content(
        [YES_OR_NO_SYSTEM_PROMPT, user_prompt], YES_OR_NO_SCHEMA
    )

    return intent["value"], tokens


async def get_analyze_expense_trend(bills, categories):
    system_prompt = ANALYZE_EXPENSE_TREND_PROMPT.format(bills=bills)

    return await generate_content(system_prompt)


async def generate_content(contents, schema=None):
    response = await client.aio.models.generate_content(
        model=LLM_MODEL,
        contents=contents,
        config=get_config(schema),
    )
    logger = Logger()
    logger.info(response.text)

    if schema is not None:
        resp = json.loads(response.text)
    else:
        resp = response.text

    return resp, response.usage_metadata.total_token_count
