from datetime import datetime
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)


class Logger:
    def __init__(self, transaction_id=None):
        self.logger = logging.getLogger()
        self.transaction_id = transaction_id or ""

    def set_transaction_id(self, transaction_id):
        self.transaction_id = transaction_id
        format = "%(asctime)s - %(levelname)s - %(transaction_id)s - %(message)s"
        formatter = logging.Formatter(format)
        self.logger.handlers[0].setFormatter(formatter)

    def log(self, level, message):
        self.logger.log(level, message)

    def info(self, message):
        self.logger.info(message)

    def error(self, message):
        self.logger.error(message)


def formatted_date(date: str | datetime) -> str:
    if isinstance(date, datetime):
        return date.strftime("%Y-%m-%d")
    else:
        return date


def sql_today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def create_whatsapp_aligned_text(title: str, lines: dict) -> str:
    text = f"```{title}"

    longest = max([len(header) for header in lines.keys()])

    for header, value in lines.items():
        spaces = longest - len(header) + 1
        text += f"\n{header}{' ' * spaces}{value}"

    return text + "```"
