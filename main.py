import asyncio
import signal

from sqlalchemy import and_
from src import amqp
from src import util
from src.cfg.database import SessionLocal
from src.model import User
from src.model import select
from src.service import MessageProcessor
from src.service.conversation import send_message


async def send_users_notifications_about_new_versions():
    def format_changelog(changelog):
        text = ""
        for i in range(len(changelog)):
            text += f"{i + 1}. {changelog[i]};\n"

        return text

    with SessionLocal() as session:
        current_version = util.get_current_version()

        users_to_notify = session.execute(
            select(User).filter(
                and_(
                    User.last_version_notified < current_version,
                    User.send_notification.is_(True),
                )
            )
        ).scalars()

        for user in users_to_notify:
            versions_to_notify = util.get_version_changes(user.last_version_notified)
            for version_data in versions_to_notify:
                version = version_data["version"]
                changelog = version_data["changelog"]

                message = (
                    f"Nova atualização! Versão *{version}*\n\n"
                    "*Novas funcionalidades*\n"
                    f"{format_changelog(changelog)}\n\n"
                    "Se você não deseja mais receber esse tipo de notificação, "
                    "é só me dizer!"
                )

                await send_message(message, phone_number=user.phone_number)

        user.last_version_notified += len(versions_to_notify)

        session.commit()


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

    event_loop.run_until_complete(send_users_notifications_about_new_versions())

    event_loop.run_until_complete(message_processor.start())
