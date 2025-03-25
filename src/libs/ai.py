from datetime import datetime
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


def get_now():
    return datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).isoformat()


def get_intent_system_prompt():
    return """
    Você é um assistente que ajuda a descobrir a intenção de uma mensagem.
    Responda com um json no formato: {'intent': user_intent}
    Essas são as possibilidades e o que deve ser retornado:
        1. Ele pode enviar uma mensagem com os dados de uma compra. Será sempre uma afirmação.
            Nesse caso, user_intent deve ser 'register_bill'.
        2. Ele pode enviar uma mensagem com uma pergunta sobre os gastos em um determinado período.
            Nesse caso, user_intent deve ser 'sum_bills'.
        3. Ele pode enviar uma mensagem com informações sobre uma categoria de gastos.
            Nesse caso, user_intent deve ser 'register_category'.
        4. Ele pode enviar uma mensagem pedindo para excluir uma conta.
            Nesse caso, user_intent deve ser 'delete_bill'.
    Caso o pedido do usuário não se encaixe nessas opções, retorne user_intent 'unknown'.
    """


def get_register_bill_system_prompt(categories):
    return f"""
    Retorne um json no formato {{'value': bill_value, 'category': category, 'date': bill_date}}.
    Caso não seja indicado uma data, entenda como o dia atual em UTC.
    Para os exemplos, cosidere a data atual sendo '2025-03-16T00:00:00-00:00'
    Exemplos:
        'Gastei 20,30 em lanche': {{'value': 20.30, 'category': {{'id': 1, 'name': 'food'}}, 'date': '2025-03-16T00:00:00-00:00'}};
        'Comprei um chapéu de 50 reais ontem': {{'value': 50.00, 'category': {{'id': 2, 'name': 'clothing'}}, 'date': '2025-03-15T00:00:00-00:00'}};
        'Comprei uma boneca terça feira de 10 reais': {{'value': 10.00, 'category': {{'id': 3, 'name': 'default'}}, 'date': '2025-03-16T00:00:00-00:00'}};
        'Gastei 10 reais em bolacha esse mês': {{'value': 10.00, 'category': {{'id': 1, 'name': 'food'}}, 'date': '2025-03-01T00:00:00-00:00'}}
    As categorias possíveis para esse usuário são: {categories}
    O dia de hoje é {get_now()}
    """


def get_read_bills_system_prompt(categories):
    return f"""
    Retorne um json no formato {{'category': category, 'from': initial_date, 'until': final_date}}.
    Para os exemplos, cosidere a data atual sendo '2025-03-16T00:00:00-00:00'
    Exemplos:
        'Quanto gastei com comida esse mês?': {{'category': {{'id': 1, 'name': 'food'}}, 'from': '2025-03-1T00:00:00-00:00', 'until': '2025-04-01T00:00:00-00:00'}};
        'Quanto foi meu consumo de mercado mês passado?': {{'category': {{'id': 2, 'name': 'market'}}, 'from': '2025-02-01T00:00:00-00:00', 'until': '2025-03-01T00:00:00-00:00'}};
        'Quanto gastei em outubro?' {{'category': null, 'from': '2024-10-01T00:00:00-00:00', 'until': '2024-11-01T00:00:00-00:00'}};
        'Quanto gastei essa semana com diversos?': {{'category': {{'id': 2, 'name': 'default'}}, 'from': '2025-03-10T00:00:00-00:00', 'until': '2025-03-17T00:00:00-00:00'}}
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
    system_prompt = get_intent_system_prompt()

    intent_json = await generate_ai_response(system_prompt, user_prompt)

    return intent_json["intent"]


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
    message = response.json()["choices"][0]["message"]["content"]

    return json.loads(message)


async def close_httpx_client():
    httpx_client.aclose()
