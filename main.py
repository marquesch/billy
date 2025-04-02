import asyncio
import signal

from src import amqp
from src.cfg.database import SessionLocal
from src.service import MessageProcessor
from src.service.step.background import set_background_task_manager

if __name__ == "__main__":
    shutdown_event = asyncio.Event()

    message_processor = MessageProcessor(SessionLocal, shutdown_event)
    background_task_manager = set_background_task_manager(shutdown_event)

    event_loop = asyncio.get_event_loop()

    event_loop.add_signal_handler(
        signal.SIGINT, lambda: asyncio.create_task(shutdown_event.set())
    )

    event_loop.add_signal_handler(
        signal.SIGTERM, lambda: asyncio.create_task(shutdown_event.set())
    )

    event_loop.run_until_complete(amqp.connect_amqp_client())

    event_loop.create_task(background_task_manager.work())
    event_loop.create_task(message_processor.start())

    try:
        event_loop.run_until_complete(shutdown_event.wait())
    finally:
        event_loop.run_until_complete(message_processor.close())
        event_loop.run_until_complete(background_task_manager.close())
        event_loop.close()
