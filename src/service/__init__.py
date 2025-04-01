import asyncio
import json
import traceback

from src import util
from src.amqp import AMQP_RECEIVE_MESSAGE_QUEUE
from src.amqp import amqp_client
from src.database import RedisClient
from src.database import db_session_manager
from src.schema import ReceiveMessagePayload
from src.service.conversation import ConversationManager

import aio_pika


class MessageProcessor:
    def __init__(self, session_factory, phone_number):
        self.session_factory = session_factory
        self.redis_client = RedisClient()
        self.logger = util.Logger()
        self.shutdown_event = asyncio.Event()
        self.phone_number = phone_number

    async def start(self):
        await amqp_client.consume(AMQP_RECEIVE_MESSAGE_QUEUE, self._process_message)

        self.logger.info("Started consuming messages")

        await self.shutdown_event.wait()

    async def close(self):
        self.logger.info("Shutting down MessageProcessor")

        self.shutdown_event.set()

        await asyncio.gather(
            amqp_client.close(),
            asyncio.to_thread(self.redis_client.close()),
        )

        self.logger.info("Shutdown complete")

    @util.time_execution(message="Time to process message: ")
    async def _process_message(self, message: aio_pika.IncomingMessage):
        async with message.process():
            message_data = json.loads(message.body)
            message_payload = ReceiveMessagePayload(**message_data)

            if message_payload.sender_number == self.phone_number:
                return

            lock = f"user:{message_payload.sender_number}:lock"

            logger_ctx_token = util.set_logger(message_payload.transaction_id)

            if self.redis_client.acquire_lock(lock) is None:
                self.logger.info(f"{message_payload.sender_number} locked")
                return

            try:
                logger = util.get_logger()
                logger.info("Got message")
                logger.info("Checking state on redis")

                state = self._get_conversation_state(message_payload.sender_number)

                with db_session_manager() as session:
                    conversation_manager = ConversationManager(message_payload, state)
                    tokens_used, state = await conversation_manager.process()
                    session.commit()

                logger.info("Saving session info on redis")

                self._save_conversation_state(message_payload.sender_number, state)

                self._cache_token_usage(message_payload.transaction_id, tokens_used)

            except Exception:
                traceback.print_exc()

            finally:
                self.redis_client.release_lock(lock)
                util.reset_logger(logger_ctx_token)

    def _cache_token_usage(self, transaction_id, tokens_used):
        self.redis_client.set(
            f"{self.phone_number}:token_usage:{transaction_id}",
            tokens_used,
        )

    def _save_conversation_state(self, phone_number, state):
        self.redis_client.set(f"{phone_number}:state", state)

    def _get_conversation_state(self, phone_number):
        return self.redis_client.get(f"{phone_number}:state", {})

    def _check_user_lock(self, phone_number):
        lock = f"user:{phone_number}:lock"

        if self.redis_client.acquire_lock(lock) is None:
            self.logger.info(f"{phone_number} locked")
            return

        return lock
