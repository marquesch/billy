from datetime import datetime
from datetime import timedelta
import random
import re
from typing import ClassVar

from src import database
from src import util
from src.lib import ai
from src.model import Bill
from src.model import Category
from src.model import Tenant
from src.model import User
from src.schema import StepResult
from src.util import create_whatsapp_aligned_text
from src.util import formatted_date

from sqlalchemy import and_
from sqlalchemy import delete
from sqlalchemy import func
from sqlalchemy import select


class Step:
    registry: ClassVar = {}

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        Step.registry[cls.__name__] = cls

    def __init__(self, user, state):
        self.user = user
        self.state = state
        self.session = database.get_db_session()
        self.log = util.get_logger()

    async def process(self, message_payload):
        self.log.info(f"Processing step: {self.__class__.__name__}")
        result = await self._process(message_payload)

        if result.waiting_for_response:
            self.state["next_step"] = result.next_step

        return result

    async def _process(self, message_payload):
        raise NotImplementedError


class WaitingStep(Step):
    async def _process(self, message_payload):
        message = self.question
        next_step = self.next_step

        return StepResult(
            message=message, next_step=next_step, waiting_for_response=True
        )

    @property
    def question(self) -> str:
        raise NotImplementedError

    @property
    def next_step(self) -> str:
        raise NotImplementedError


class TerminalStep(Step):
    async def process(self, message_payload):
        result = await self._process(message_payload)

        self.state.clear()

        return result


class InitialHandler(Step):
    async def _process(self, message_payload):
        if not self.user:
            return StepResult(next_step="BeginRegistration")
        else:
            return StepResult(next_step="HandleUserIntent")


class HandleUserIntent(Step):
    async def _process(self, message_payload):
        system_prompt = (
            "Você é um assistente que ajuda a descobrir a intenção de uma mensagem. "
            "Estes são os possíveis conteúdos da mensagem e o que deve ser retornado"
        )
        for class_name, cls in Step.registry.items():
            if hasattr(cls, "intent_description"):
                system_prompt += f"\n{cls.intent_description}: '{class_name}'"

        tokens, user_intent = await ai.get_user_intent(
            message_payload.message_body, system_prompt
        )

        return StepResult(tokens_used=tokens, next_step=user_intent)


class BeginRegistration(Step):
    async def _process(self, message_payload):
        message = (
            "Olá, eu sou Billy, seu assistente financeiro!\n"
            "Vejo que essa é sua primeira mensagem.\n"
            "Para continuar, preciso fazer seu cadastro."
        )

        return StepResult(message=message, next_step="AskUserName")


class AskUserName(WaitingStep):
    @property
    def question(self):
        return "Qual seu nome?"

    @property
    def next_step(self):
        return "ProcessUserName"


class ProcessUserName(Step):
    async def _process(self, message_payload):
        self.state["name"] = message_payload.message_body

        return StepResult(next_step="AskUserDefaultCategories")


class AskUserDefaultCategories(WaitingStep):
    @property
    def question(self) -> str:
        return (
            "Quer cadastrar categorias recomendadas? São as seguintes: "
            f"{[category for category in Category.BASIC_CATEGORIES.keys()]}"
        )

    @property
    def next_step(self) -> str:
        return "ProcessUserDefaultCategories"


class ProcessUserDefaultCategories(Step):
    async def _process(self, message_payload):
        tokens, register_default_categories = await ai.get_yes_or_no_answer(
            message_payload.message_body
        )

        self.state["register_default_categories"] = register_default_categories

        return StepResult(tokens_used=tokens, next_step="AskUserRegisterFakeBills")


class AskUserRegisterFakeBills(WaitingStep):
    @property
    def question(self) -> str:
        return "Quer gerar contas falsas?"

    @property
    def next_step(self) -> str:
        return "ProcessUserRegisterFakeBills"


class ProcessUserRegisterFakeBills(Step):
    async def _process(self, message_payload):
        tokens, register_fake_bills = await ai.get_yes_or_no_answer(
            message_payload.message_body
        )

        self.state["register_fake_bills"] = register_fake_bills

        return StepResult(tokens_used=tokens, next_step="RegisterUser")


class RegisterUser(TerminalStep):
    async def _process(self, message_payload):
        register_fake_bills = self.state["register_fake_bills"]
        register_default_categories = self.state["register_default_categories"]

        tenant = Tenant()
        self.session.add(tenant)
        self.session.flush()
        self.session.refresh(tenant)

        categories = [
            Category(
                name=Category.DEFAULT_CATEGORY["name"],
                description=Category.DEFAULT_CATEGORY["description"],
                tenant_id=tenant.id,
            )
        ]

        if register_default_categories:
            categories.extend(
                [
                    Category(name=name, description=description, tenant_id=tenant.id)
                    for name, description in Category.BASIC_CATEGORIES.items()
                ]
            )

        user = User(
            name=self.state["name"],
            phone_number=message_payload.sender_number,
            tenant_id=tenant.id,
        )

        self.session.add_all(categories)
        self.session.add(user)
        self.session.flush()
        self.session.refresh(user)

        title = "*Registro concluído com sucesso!*"

        if register_fake_bills:
            self.log.info("Registering fake bills")

            total = _register_fake_bills(
                categories, message_payload.message_id, user, self.session
            )

            title = (
                "*Registro concluído com sucesso!*\n"
                f"Cadastrei também {total} contas falsas. "
                "Caso queira excluí-las, é só pedir!"
            )

        message = create_whatsapp_aligned_text(
            title,
            {
                "Nome": user.name,
                "Número de telefone": user.phone_number,
                "Tokens por hora": user.tokens_per_hour,
                "Contas falsas?": "Sim" if register_fake_bills else "Não",
            },
        )

        return StepResult(message=message)


class RegisterBill(TerminalStep):
    intent_description = "Dados sobre uma compra"

    async def _process(self, message_payload):
        categories = [
            category.to_dict()
            for category in Category.get_all(self.session, self.user.tenant_id)
        ]

        tokens, bill_to_register = await ai.get_bill_to_register(
            message_payload.message_body, categories
        )

        bill = Bill(
            value=bill_to_register["value"],
            date=bill_to_register["date"],
            original_prompt=message_payload.message_body,
            category_id=bill_to_register["category_id"],
            tenant_id=self.user.tenant_id,
            message_id=message_payload.message_id,
        )

        self.session.add(bill)
        self.session.flush()

        message = create_whatsapp_aligned_text(
            "Conta registrada",
            {
                "Valor": bill.value,
                "Categoria": bill.category.name,
                "Data": formatted_date(bill.date),
            },
        )

        return StepResult(tokens_used=tokens, message=message)


class RegisterCategory(TerminalStep):
    intent_description = "Pedido para criar uma categoria de despesa"

    async def _process(self, message_payload):
        tokens, category_dict = await ai.get_category_to_register(
            message_payload.message_body
        )

        category = Category(
            **category_dict,
            tenant_id=self.user.tenant_id,
        )

        self.session.add(category)
        self.session.flush()

        message = create_whatsapp_aligned_text(
            "Categoria registrada",
            {
                "Nome": category.name,
                "Descrição": category.description,
            },
        )

        return StepResult(tokens_used=tokens, message=message)


class DeleteBill(TerminalStep):
    intent_description = "Pedido para deletar uma conta"

    async def _process(self, message_payload):
        message = (
            "Para que eu possa entender qual mensagem você quer excluir, "
            "por favor, responda à mensagem que você enviou que "
            "criou a conta que vocé quer excluir."
        )

        if message_payload.quoted_message_id is not None:
            bill_to_delete = Bill.get_by_message_id(
                self.session, self.user.tenant_id, message_payload.quoted_message_id
            )

            message = (
                "Não consegui encontrar a conta a ser excluída. "
                "Ou ela já foi excluída ou você respondeu a mensagem errada."
            )

            if bill_to_delete is not None:
                message = create_whatsapp_aligned_text(
                    "Conta excluida",
                    {
                        "Valor": bill_to_delete.value,
                        "Categoria": bill_to_delete.category.name,
                        "Data": formatted_date(bill_to_delete.date),
                    },
                )

                self.session.delete(bill_to_delete)

        return StepResult(message=message)


class SumBills(TerminalStep):
    intent_description = (
        "Pedido de quanto ele gastou em um período ou em um dia específico"
    )

    async def _process(self, message_payload):
        categories = {
            category.id: category.to_dict()
            for category in Category.get_all(self.session, self.user.tenant_id).all()
        }

        tokens, query_data = await ai.get_bills_query_data(
            message_payload.message_body, categories.values()
        )

        category_name = None

        filters = [Bill.tenant_id == self.user.tenant_id]

        if len(query_data["range"]) == 1:
            filters.append(Bill.date == query_data["range"][0])
        else:
            filters.append(Bill.date.between(*query_data["range"]))

        if category_id := query_data.get("category_id", None):
            filters.append(Bill.category_id == category_id)
            category_name = categories[category_id]["name"]

        query = select(func.sum(Bill.value)).where(and_(*filters))

        sum_value = self.session.execute(query).scalar() or 0

        message = "Soma das contas "
        if len(query_data["range"]) == 1:
            day = query_data["range"][0]
            message += f"do dia {formatted_date(day)}"
        else:
            begin, end = query_data["range"]
            message += f"entre {formatted_date(begin)} e {formatted_date(end)}"

        if category_name is not None:
            message += f" da categoria {category_name}"

        message += f":\n*R${sum_value:.2f}*"

        return StepResult(tokens_used=tokens, message=message)


class ListCategories(TerminalStep):
    intent_description = "Pedido para listar categorias"

    async def _process(self, message_payload):
        categories = [
            {"Nome": category.name, "Descrição": category.description}
            for category in Category.get_all(self.session, self.user.tenant_id).all()
        ]

        message = create_whatsapp_aligned_text("Categorias", categories)

        return StepResult(message=message)


class RegisterFakeBills(TerminalStep):
    intent_description = "Pedido para registrar contas falsas"

    async def _process(self, message_payload):
        self.log.info(self.user.generated_fake_bills)
        if self.user.generated_fake_bills:
            message = (
                "Você já gerou contas falsas. Infelizmente, "
                "eu não posso fazer esse processo novamente."
            )
            return StepResult(message=message)

        categories = Category.get_all(self.session, self.user.tenant_id).all()

        self.log.info("Registering fake bills")

        total = _register_fake_bills(
            categories, message_payload.message_id, self.user, self.session
        )

        self.user.tenant.generated_fake_bills = True
        self.session.flush()

        message = f"Criei um total de {total} contas falsas!"

        return StepResult(message=message)


class DeleteFakeBills(TerminalStep):
    intent_description = "Pedido para deletar contas falsas"

    async def _process(self, message_payload):
        self.log.info("Deleting fake bills")

        count = self.session.execute(
            delete(Bill).where(
                and_(Bill.tenant_id == self.user.tenant_id, Bill.fake.is_(True))
            )
        ).rowcount

        message = (
            f"Removi todas as suas contas falsas.\nRemovi um total de *{count}* contas."
        )

        return StepResult(message=message)


class AnalyzeExpenses(TerminalStep):
    intent_description = "Pedido para analisar gastos"

    async def _process(self, message_payload):
        categories = [
            category.to_dict()
            for category in Category.get_all(self.session, self.user.tenant_id).all()
        ]

        tokens_used = 0

        tokens, query_data = await ai.get_bills_query_data(
            message_payload.message_body, categories
        )

        tokens_used += tokens

        params = dict(session=self.session, tenant_id=self.user.tenant_id)

        if len(query_data["range"]) == 1:
            params["date"] = query_data["range"][0]
        else:
            params["date_range"] = query_data["range"]

        if category_id := query_data.get("category_id", None):
            params["category_id"] = category_id

        bills = Bill.get_many(**params)

        tokens, analysis = await ai.get_expenses_analysis(categories, bills)

        tokens_used += tokens

        return StepResult(tokens_used=tokens_used, message=analysis)


class Courtesy(TerminalStep):
    intent_description = "Se o usuário estiver somente agradecendo"

    async def _process(self, message_payload):
        tokens_used, message = await ai.get_courtesy_answer(
            message_payload.message_body
        )

        return StepResult(tokens_used=tokens_used, message=message)


class InviteFamilyMember(WaitingStep):
    intent_description = "Se o usuário deseja convidar um membro da família"

    @property
    def question(self):
        return "Qual o número de telefone do membro da família?"

    @property
    def next_step(self):
        return "ProcessInviteFamilyMember"


class ProcessInviteFamilyMember(Step):
    async def _process(self, message_payload):
        message_body = message_payload.message_body

        # TODO create logic. send to db?
        phone_number = re.sub(r"\D", "", message_body)

        ...


class Unknown(TerminalStep):
    intent_description = "Se o pedido do usuário não se encaixa em nenhuma outra opção"

    async def _process(self, message_payload):
        message = "Eu não entendi o que você disse."

        return StepResult(message=message)


def _register_fake_bills(categories, message_id, user, session):
    bills = []
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    for i in range(365):
        for _ in range(random.randint(1, 3)):
            category = random.choice(categories)
            value = random.randint(1, 1000)
            date = today - timedelta(days=i)

            bill = Bill(
                value=value,
                date=date,
                category_id=category.id,
                tenant_id=user.tenant_id,
                message_id=message_id,
                fake=True,
            )

            bills.append(bill)

    user.generated_fake_bills = True

    session.add_all(bills)
    session.flush()
    session.refresh(user)

    return len(bills)
