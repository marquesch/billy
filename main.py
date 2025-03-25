import asyncio
from datetime import datetime
import json
import logging
import os
import sys

import aio_pika
from src.amqp import AMQPClient
from src.cfg.database import RedisClient
from src.cfg.database import SessionLocal
from src.cfg.database import init_db
from src.libs.ai import close_httpx_client
from src.libs.ai import get_bill_to_register
from src.libs.ai import get_bills_to_sum_query_data
from src.libs.ai import get_category_to_register
from src.libs.ai import get_user_intent
from src.libs.step import Step
from src.repository import BillRepository
from src.repository import CategoryRepository
from src.repository import TenantRepository
from src.repository import UserRepository
from src.schema import ReceiveMessagePayload
from src.schema import SendMessagePayload
from src.util import formatted_date

AMQP_HOST = os.getenv("AMQP_HOST", "rabbitmq")
AMQP_PORT = int(os.getenv("AMQP_PORT", 5672))
AMQP_USER = os.getenv("AMQP_USER", "billy")
AMQP_PASSWORD = os.getenv("AMQP_PASSWORD", "billy")


AMQP_RECEIVE_MESSAGE_QUEUE = "q.message.receive"
AMQP_SEND_MESSAGE_QUEUE = "q.message.send"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)


class MessageProcessor:
    def __init__(
        self,
        client: AMQPClient,
        receive_queue,
        send_queue,
        session_factory,
    ):
        self.client = client
        self.receive_queue = receive_queue
        self.send_queue = send_queue
        self.session_factory = session_factory
        self.redis_client = RedisClient()

    async def start(self):
        await self.client.connect()
        await self.client.consume(self.receive_queue, self._process_message)
        logging.info("Started consuming messages")
        await asyncio.Future()

    async def _process_message(self, message: aio_pika.IncomingMessage):
        async with message.process():
            message_data = json.loads(message.body)
            message_payload = ReceiveMessagePayload(**message_data)

            logging.info(f"{message_payload.transaction_id} - Got message")

            session_info = self.redis_client.get(
                f"{message_payload.sender_number}:session_info", {}
            )

            current_step = Step(session_info, message_payload.sender_number).process(
                message_payload.message_body
            )

            if current_step.message is not None:
                response_payload = SendMessagePayload(
                    message_type="text",
                    recipient_number=message_payload.sender_number,
                    message_body=current_step.message,
                    transaction_id=message_payload.transaction_id,
                    quoted_message_id=message_payload.message_id,
                )

                body = json.dumps(response_payload.model_dump())

                logging.info(f"{message_payload.transaction_id} - Sending back message")

                await self.client.publish(body, self.send_queue)

            self.redis_client.set(
                f"{message_payload.sender_number}:session_info",
                current_step.session_info,
            )

            # logging.info(f"{message_payload.transaction_id} - Checking user intent")
            # with self.session_factory() as session:
            #     user_repo = UserRepository(session)

            #     user = user_repo.get_by_phone_number(message_payload.sender_number)

            #     if user is None:
            #         logging.info(
            #             f"{message_payload.transaction_id} - User isn't registered. Registering user"
            #         )

            #         user = self._register_user(session, message_payload.sender_number)

            #     response_text = await self._handle_intent(
            #         session, message_payload, user
            #     )

            # response_payload = SendMessagePayload(
            #     message_type="text",
            #     recipient_number=message_payload.sender_number,
            #     message_body=response_text,
            #     transaction_id=message_payload.transaction_id,
            #     quoted_message_id=message_payload.message_id,
            # )

            # body = json.dumps(response_payload.model_dump())

            # logging.info(f"{message_payload.transaction_id} - Sending back message")

            # await self.client.publish(body, self.send_queue)

    async def _register_bill(self, session, message_payload, tenant_id):
        category_repo = CategoryRepository(session, tenant_id)
        bill_repo = BillRepository(session, tenant_id)

        categories = [category.to_dict() for category in category_repo.get_all()]

        bill_to_register = await get_bill_to_register(
            message_payload.message_body, categories
        )

        bill = bill_repo.create(
            value=bill_to_register["value"],
            date=bill_to_register["date"],
            original_prompt=message_payload.message_body,
            message_id=message_payload.message_id,
            category_id=bill_to_register["category"]["id"],
            tenant_id=tenant_id,
        )

        return bill

    async def _sum_bills(self, session, user_prompt, tenant_id):
        category_repo = CategoryRepository(session, tenant_id)
        bill_repo = BillRepository(session, tenant_id)

        categories = [category.to_dict() for category in category_repo.get_all()]

        query_data = await get_bills_to_sum_query_data(user_prompt, categories)

        category_id, category_name = None, None
        if query_data["category"] is not None:
            category_id, category_name = query_data["category"].values()

        sum = bill_repo.get_sum_by_date_range(
            query_data["from"], query_data["until"], category_id
        )

        return sum, category_name, query_data["from"], query_data["until"]

    async def _handle_intent(self, session, message_payload, user):
        user_intent = await get_user_intent(message_payload.message_body)

        tenant_id = user.tenant_id

        match user_intent:
            case "register_bill":
                logging.info(f"{message_payload.transaction_id} - Registering bill")

                bill = await self._register_bill(session, message_payload, tenant_id)

                response_text = (
                    f"*Bill created*\n"
                    f"*```Value```*```      {bill.value}```\n"
                    f"*```Category```*```   {bill.category.name}```\n"
                    f"*```Date```*```       {formatted_date(bill.date)}```\n"
                )

            case "register_category":
                logging.info(f"{message_payload.transaction_id} - Registering category")

                category = await self._register_category(
                    session, message_payload, tenant_id
                )

                response_text = "*Category created*\n"
                if category.description is not None:
                    description = (
                        category.description
                        if category.description is not None
                        else "null"
                    )
                    response_text += f"*```Description```*```   {description}```"

            case "sum_bills":
                logging.info(f"{message_payload.transaction_id} - Summing bills")

                sum, category_name, from_, until = await self._sum_bills(
                    session, message_payload.message_body, tenant_id
                )

                from_ = datetime.fromisoformat(from_)
                until = datetime.fromisoformat(until)

                response_text = "*Total spent*\n"
                if category_name is not None:
                    response_text += f"*```on```*```    {category_name}```\n"
                response_text += (
                    f"*```from```*```  {from_.strftime('%d/%m/%y')}```\n"
                    f"*```until```*``` {until.strftime('%d/%m/%y')}```\n"
                    f"{sum}"
                )

            case "delete_bill":
                logging.info(f"{message_payload.transaction_id} - Deleting bill")
                bill_repo = BillRepository(session, tenant_id)

                bill_to_delete = bill_repo.get_by_message_id(
                    message_payload.quoted_message_id
                )

                if bill_to_delete is not None:
                    response_text = (
                        f"*Bill deleted*"
                        f"*```Value```*```     {bill_to_delete.value}```"
                        f"*```Category```*```  {bill.category.name}```"
                        f"*```Date```*```      {formatted_date(bill.date)}```"
                    )

                    bill_repo.delete(bill_to_delete.id)

                else:
                    response_text = "Could not find bill."

            case _:
                response_text = "I'm sorry, I didn't understand that."

        return response_text

    async def _register_category(self, session, message_payload, tenant_id):
        category_dict = await get_category_to_register(message_payload.message_body)

        category_repo = CategoryRepository(session, tenant_id)

        category = category_repo.create(
            category_dict["name"], category_dict["description"]
        )

        return category

    def _register_user(self, session, number):
        tenant_repo = TenantRepository(session)
        tenant = tenant_repo.create()

        user_repo = UserRepository(session)

        user = user_repo.create(number, tenant.id)

        category_repo = CategoryRepository(session, tenant.id)

        category_repo.create("default", "Default category")

        return user


async def main():
    global client

    client = AMQPClient(
        host=AMQP_HOST, port=AMQP_PORT, login=AMQP_USER, password=AMQP_PASSWORD
    )

    message_processor = MessageProcessor(
        client,
        AMQP_RECEIVE_MESSAGE_QUEUE,
        AMQP_SEND_MESSAGE_QUEUE,
        SessionLocal,
    )

    await message_processor.start()


if __name__ == "__main__":
    logging.info("Initializing database")
    init_db()
    asyncio.run(main())
    close_httpx_client()
