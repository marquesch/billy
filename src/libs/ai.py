from datetime import datetime
from enum import Enum
import json
import os

from httpx import AsyncClient

API_KEY = os.getenv("AI_PLATFORM_API_KEY")
BASE_URL = os.getenv("AI_PLATFORM_BASE_URL", "").strip("/")
COMPLETION_URL = f"{BASE_URL}/chat/completions"

headers = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "Authorization": f"Bearer {API_KEY}",
}

httpx_client = AsyncClient()


class InitialIntentTypes(Enum):
    UNKNOWN = 0
    REGISTER_BILL = 1
    SUM_BILLS = 2
    REGISTER_CATEGORY = 3
    DELETE_BILL = 4
    LIST_CATEGORIES = 5


def get_now():
    return datetime.now().strftime("%Y-%m-%d")


def get_initial_intent_system_prompt():
    return f"""
    Você é um assistente que ajuda a descobrir a intenção de uma mensagem.
    Responda com um json no formato: {{'intent': user_intent}}
    Essas são as possibilidades de conteúdo da mensagem e o que deve ser retornado:
        1. Dados de uma compra. user_intent={InitialIntentTypes.REGISTER_BILL.value}
        2. Pergunta sobre os gastos em um determinado período. user_intent={InitialIntentTypes.SUM_BILLS.value}
        3. Nome de uma categoria de gastos. user_intent={InitialIntentTypes.REGISTER_CATEGORY.value}
        4. Pedindo para excluir uma conta. user_intent={InitialIntentTypes.DELETE_BILL.value}.
        5. Pedindo para listar categorias. user_intent={InitialIntentTypes.LIST_CATEGORIES.value}.
    Caso o pedido do usuário não se encaixe nessas opções, intent_type={InitialIntentTypes.UNKNOWN.value}.
    """


def get_register_bill_system_prompt(categories):
    return f"""
    Retorne um json no formato {{'value': bill_value, 'category': category, 'date': bill_date}}.
    Caso não seja indicado uma data, entenda como o dia atual em UTC.
    Para os exemplos, cosidere a data atual sendo '2025-03-16' e as categorias [{{'id': 1, 'name': 'comida'}}, {{'id': 2, 'name': 'mercado'}}, {{'id': 3, 'name': 'default'}}]
    Exemplos:
        'Gastei 20,30 em lanche': {{'value': 20.30, 'category_id': 1, 'date': '2025-03-16'}};
        'Comprei um chapéu de 50 reais ontem': {{'value': 50.00, 'category_id': 2, 'date': '2025-03-15'}};
        'Comprei uma boneca terça feira de 10 reais': {{'value': 10.00, 'category_id': 3, 'date': '2025-03-16'}};
        'Gastei 10 reais em bolacha esse mês': {{'value': 10.00, 'category_id': 1, 'date': '2025-03-01'}}
    As categorias possíveis para esse usuário são: {categories}
    O dia de hoje é {get_now()}
    """


def get_read_bills_system_prompt(categories):
    return f"""
    Retorne um json no formato {{'category': category_id, 'from': initial_date, 'until': final_date}}.
    Para os exemplos, cosidere a data atual sendo '2025-03-16'
    Exemplos:
        'Quanto gastei com comida esse mês?': {{'category_id': 1, 'from': '2025-03-1', 'until': '2025-04-01'}};
        'Quanto foi meu consumo de mercado mês passado?': {{'category_id': 2, 'from': '2025-02-01', 'until': '2025-03-01'}};
        'Quanto gastei em outubro?' {{'category_id': null, 'from': '2024-10-01', 'until': '2024-11-01'}};
        'Quanto gastei essa semana com diversos?': {{'category_id': 3, 'from': '2025-03-10', 'until': '2025-03-17'}}
    As categorias possíveis para esse usuário são: {categories}
    O dia de hoje é {get_now()}
    """


def get_register_category_system_prompt():
    return """
    Retorne um json no formato {'name': category_name, 'description': category_description}.
    Exemplos:
        'Crie uma categoria de gastos chamada mercado': {'name': 'market', 'description': 'Gastos com mercado'}
        'Vou criar uma categoria de gastos chamada diversão': {'name': 'fun', 'description': 'Gastos com diversão'}
    """


def base_json_data(system_prompt, user_prompt):
    return dict(
        model="deepseek-chat",
        max_tokens=1000,
        response_format=dict(type="json_object"),
        temperature=0,
        messages=[
            dict(role="system", content=system_prompt),
            dict(role="user", content=user_prompt),
        ],
    )


async def get_user_intent(user_prompt):
    system_prompt = get_initial_intent_system_prompt()

    intent_json, tokens = await generate_ai_response(system_prompt, user_prompt)

    return InitialIntentTypes(intent_json["intent"]), tokens


async def get_bill_to_register(user_prompt, categories):
    system_prompt = get_register_bill_system_prompt(categories)

    return await generate_ai_response(system_prompt, user_prompt)


async def get_bills_to_sum_query_data(user_prompt, categories):
    system_prompt = get_read_bills_system_prompt(categories)

    return await generate_ai_response(system_prompt, user_prompt)


async def get_category_to_register(user_prompt):
    system_prompt = get_register_category_system_prompt()

    return await generate_ai_response(system_prompt, user_prompt)


async def generate_ai_response(system_prompt, user_prompt):
    data = base_json_data(system_prompt, user_prompt)
    response = await httpx_client.post(
        url=COMPLETION_URL, json=data, headers=headers, timeout=30
    )

    response_json = response.json()

    tokens = response_json["usage"]["completion_tokens"]
    message = response_json["choices"][0]["message"]["content"]

    return json.loads(message), tokens


async def close_httpx_client():
    httpx_client.aclose()
