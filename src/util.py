from datetime import datetime
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)


class TransactionFilter(logging.Filter):
    def __init__(self, transaction_id):
        super().__init__()
        self.transaction_id = transaction_id

    def filter(self, record):
        record.transaction_id = self.transaction_id
        return True


class Logger:
    def __init__(self, transaction_id=None, name=None):
        if transaction_id is not None:
            name = "transaction_logger_" + transaction_id
        self.logger = logging.Logger(name, level=logging.INFO)
        self.logger.addHandler(logging.StreamHandler(sys.stdout))
        format = "%(asctime)s - %(levelname)s - %(message)s"

        if transaction_id is not None:
            format = "%(asctime)s - %(levelname)s - %(transaction_id)s - %(message)s"
            self.logger.addFilter(TransactionFilter(transaction_id))

        self.logger.handlers[0].setFormatter(logging.Formatter(format))

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


def create_whatsapp_aligned_text(title: str, lines: dict | list[dict]) -> str:
    def iterate_dict(d: dict, l: int):
        t = ""
        for header, value in d.items():
            spaces = l - len(header) + 5
            t += f"\n{header}{' ' * spaces}{value}"

        return t

    text = "```"
    if title:
        text += f"{title}"

    if isinstance(lines, dict):
        longest = max([len(header) for header in lines.keys()])
        text += iterate_dict(lines, longest)
    elif isinstance(lines, list):
        longest = max([len(header) for header in lines[0].keys()])
        for line in lines:
            text += iterate_dict(line, longest)
            text += "\n"

    return text + "```"
