import asyncio
import signal

from src import amqp
from src.cfg.database import SessionLocal
from src.service import MessageProcessor

if __name__ == "__main__":
    message_processor = MessageProcessor(SessionLocal)

    event_loop = asyncio.get_event_loop()

    event_loop.add_signal_handler(
        signal.SIGINT, lambda: asyncio.create_task(message_processor.close())
    )

    event_loop.add_signal_handler(
        signal.SIGTERM, lambda: asyncio.create_task(message_processor.close())
    )

    event_loop.run_until_complete(amqp.connect_amqp_client())

    event_loop.run_until_complete(message_processor.start())
