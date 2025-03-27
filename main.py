import asyncio
import json
import os
import signal
import time

import aio_pika
from src.amqp import AMQPClient
from src.cfg.database import RedisClient
from src.cfg.database import SessionLocal
from src.cfg.database import init_db
from src.libs.step import Step
from src.schema import ReceiveMessagePayload
from src.schema import SendMessagePayload
from src.util import Logger

AMQP_HOST = os.getenv("AMQP_HOST", "rabbitmq")
AMQP_PORT = int(os.getenv("AMQP_PORT", 5672))
AMQP_USER = os.getenv("AMQP_USER", "billy")
AMQP_PASSWORD = os.getenv("AMQP_PASSWORD", "billy")


AMQP_RECEIVE_MESSAGE_QUEUE = "q.message.receive"
AMQP_SEND_MESSAGE_QUEUE = "q.message.send"


class MessageProcessor:
    def __init__(
        self,
        amqp_client: AMQPClient,
        receive_queue,
        send_queue,
        session_factory,
    ):
        self.amqp_client = amqp_client
        self.receive_queue = receive_queue
        self.send_queue = send_queue
        self.session_factory = session_factory
        self.redis_client = RedisClient()
        self.logger = Logger(name="message_processor")
        self.shutdown_event = asyncio.Event()

    async def start(self):
        await self.amqp_client.connect()
        await self.amqp_client.consume(self.receive_queue, self._process_message)

        self.logger.info("Started consuming messages")

        await self.shutdown_event.wait()

    async def close(self):
        self.logger.info("Shutting down MessageProcessor")

        self.shutdown_event.set()

        await asyncio.gather(
            self.amqp_client.close(),
            asyncio.to_thread(self.redis_client.close()),
        )

        self.logger.info("Shutdown complete")

    async def _process_message(self, message: aio_pika.IncomingMessage):
        async with message.process():
            start = time.perf_counter()
            message_data = json.loads(message.body)
            message_payload = ReceiveMessagePayload(**message_data)

            lock = f"user:{message_payload.sender_number}:lock"

            if self.redis_client.acquire_lock(lock) is None:
                self.logger.info(f"{message_payload.sender_number} locked")
                return

            transaction_logger = Logger(message_payload.transaction_id)

            transaction_logger.info("Got message")

            transaction_logger.info("Checking session info on redis")

            session_info = self.redis_client.get(
                f"{message_payload.sender_number}:session_info", {}
            )

            transaction_logger.info("Loading step")
            with self.session_factory() as session:
                current_step = await Step(
                    session_info,
                    message_payload,
                    session,
                    self.redis_client,
                    transaction_logger,
                ).process()

            transaction_logger.info("Saving session info on redis")

            self.redis_client.set(
                f"{message_payload.sender_number}:session_info",
                current_step.session_info,
            )

            if current_step.response is not None:
                response_payload = SendMessagePayload(
                    message_type="text",
                    recipient_number=message_payload.sender_number,
                    message_body=current_step.response,
                    transaction_id=message_payload.transaction_id,
                    quoted_message_id=message_payload.message_id,
                )

                body = json.dumps(response_payload.model_dump())

                transaction_logger.info("Sending back message")

                await self.amqp_client.publish(body, self.send_queue)

            end = time.perf_counter()
            transaction_logger.info(
                f"Message processed in {(end - start) * 1000:.2f} ms"
            )

            self.redis_client.release_lock(lock)


if __name__ == "__main__":
    init_db()

    client = AMQPClient(
        host=AMQP_HOST, port=AMQP_PORT, login=AMQP_USER, password=AMQP_PASSWORD
    )

    message_processor = MessageProcessor(
        client,
        AMQP_RECEIVE_MESSAGE_QUEUE,
        AMQP_SEND_MESSAGE_QUEUE,
        SessionLocal,
    )

    event_loop = asyncio.get_event_loop()

    event_loop.add_signal_handler(
        signal.SIGINT, lambda: asyncio.create_task(message_processor.close())
    )

    event_loop.add_signal_handler(
        signal.SIGTERM, lambda: asyncio.create_task(message_processor.close())
    )

    event_loop.run_until_complete(message_processor.start())
