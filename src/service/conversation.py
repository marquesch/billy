import json
import traceback

from src import database
from src import util
from src.amqp import AMQP_SEND_MESSAGE_QUEUE
from src.amqp import amqp_client
from src.model import User
from src.schema import SendMessagePayload
from src.service.step import Step

from sqlalchemy import select


class ConversationManager:
    def __init__(self, message_payload=None, state={}):
        self.message_payload = message_payload
        self.state = state
        self.session = database.get_db_session()
        self.log = util.get_logger()

        self.user = self.session.execute(
            select(User).where(User.phone_number == message_payload.sender_number)
        ).scalar()

    async def process(self):
        try:
            step = self._determine_starting_step()
            tokens_used = 0
            while True:
                result = await step.process(self.message_payload)

                tokens_used += result.tokens_used

                if result.message is not None:
                    self.log.info("Sending message")
                    await self._send_message(result.message, result.quote_message)

                if result.next_step is None or result.waiting_for_response:
                    break

                step_class = Step.registry.get(result.next_step)

                if not step_class:
                    self.log.error(f"Unknown step: {result.next_step}")
                    break

                step = step_class(self.user, self.state)

            return tokens_used, self.state
        except Exception:
            traceback.print_exc()
            await self._send_message("Ocorreu um erro ao processar sua solicitação.")

    def _determine_starting_step(self) -> Step:
        next_step = self.state.get("next_step")

        if next_step:
            step_class = Step.registry.get(next_step)
            if step_class:
                return step_class(self.user, self.state)
            else:
                self.log.info(f"Unknown next step: {next_step}, defaulting to Unknown")

        return Step.registry["Unknown"](self.user, self.state)

    async def _send_message(self, message_body, must_quote_message=False):
        quoted_message_id = None

        if must_quote_message:
            quoted_message_id = self.message_payload.message_id

        response_payload = SendMessagePayload(
            message_type="text",
            recipient_number=self.message_payload.sender_number,
            message_body=message_body,
            transaction_id=self.message_payload.transaction_id,
            quoted_message_id=quoted_message_id,
        )

        body = json.dumps(response_payload.model_dump())

        await amqp_client.publish(body, AMQP_SEND_MESSAGE_QUEUE)
