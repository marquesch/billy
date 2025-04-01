import logging
import sys
import uuid


class TransactionFilter(logging.Filter):
    def __init__(self, transaction_id):
        super().__init__()
        self.transaction_id = transaction_id

    def filter(self, record):
        record.transaction_id = self.transaction_id
        return True


class Logger:
    def __init__(self, transaction_id=None):
        name = uuid.uuid4().hex if transaction_id is None else transaction_id
        self.logger = logging.Logger(name, level=logging.INFO)
        self.logger.addHandler(logging.StreamHandler(sys.stdout))
        format = "%(asctime)s - %(levelname)s - %(message)s"
        if transaction_id is not None:
            format = "%(asctime)s - %(levelname)s - %(transaction_id)s - %(message)s"
            self.logger.addFilter(TransactionFilter(transaction_id))
        self.logger.handlers[0].setFormatter(logging.Formatter(format))

    def attach_transaction_id(self, transaction_id):
        format = "%(asctime)s - %(levelname)s - %(transaction_id)s - %(message)s"
        self.logger.addFilter(TransactionFilter(transaction_id))
        self.logger.handlers[0].setFormatter(logging.Formatter(format))

    def log(self, level, message):
        self.logger.log(level, message)

    def info(self, message):
        self.logger.info(message)

    def error(self, message):
        self.logger.error(message)
