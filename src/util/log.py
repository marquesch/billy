import logging
import sys
import uuid


class NameFilter(logging.Filter):
    def __init__(self, name):
        super().__init__()
        self.name = name

    def filter(self, record):
        record.name = self.name
        return True


class Logger:
    def __init__(self, transaction_id=None, name=None):
        name = name if name else transaction_id if transaction_id else uuid.uuid4()
        self.logger = logging.Logger(name, level=logging.INFO)
        self.logger.addHandler(logging.StreamHandler(sys.stdout))
        format = "%(asctime)s - %(levelname)s - %(name)s - %(message)s"
        self.logger.addFilter(NameFilter(name))
        self.logger.handlers[0].setFormatter(logging.Formatter(format))

    def log(self, level, message):
        self.logger.log(level, message)

    def info(self, message):
        self.logger.info(message)

    def error(self, message):
        self.logger.error(message)
