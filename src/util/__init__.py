import asyncio
from contextvars import ContextVar
from datetime import datetime
import functools
import time

from src.util.log import Logger

log_ctx: ContextVar[Logger] = ContextVar("logger_context")
background_tasks = set()


def set_logger(transaction_id=None):
    return log_ctx.set(Logger(transaction_id))


def get_logger():
    return log_ctx.get()


def reset_logger(token):
    log_ctx.reset(token)


def formatted_date(date: str | datetime) -> str:
    if isinstance(date, datetime):
        return date.strftime("%d/%m/%Y")
    else:
        return date


def sql_today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def create_whatsapp_aligned_text(title: str, lines: dict | list[dict]) -> str:
    # TODO improve this by using list instead of strings
    def iterate_dict(d: dict):
        t = ""
        for header, value in d.items():
            t += f"\n*{header}*\n```{value}```"

        return t

    text = ""

    if title:
        text += f"{title}\n"

    if isinstance(lines, dict):
        text += iterate_dict(lines)
    elif isinstance(lines, list):
        for line in lines:
            text += iterate_dict(line)
            text += "\n"

    return text


def run_in_background(func):
    def wrapped(*args, **kwargs):
        task = asyncio.create_task(func(*args, **kwargs))
        background_tasks.add(task)
        task.add_done_callback(background_tasks.discard)

    return wrapped


def time_execution(logger=None, message=""):
    if logger is None:
        logger = Logger()

    def wrapped(func):
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            start = time.perf_counter()
            result = await func(*args, **kwargs)  # Properly await async functions
            end = time.perf_counter()
            logger.info(f"{message}{(end - start) * 1000:.2f} milliseconds")
            return result

        def sync_wrapper(*args, **kwargs):
            start = time.perf_counter()
            result = func(*args, **kwargs)
            end = time.perf_counter()
            logger.info(f"{message}{(end - start) * 1000:.2f} milliseconds")
            return result

        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper

    return wrapped
