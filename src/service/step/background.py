import asyncio
from collections import deque
import os

from src import util

MAX_CONCURRENT_TASKS = int(os.getenv("MAX_CONCURRENT_TASKS", 5))

global background_task_manager


def set_background_task_manager(shutdown_event):
    # FIXME : This is a hack to avoid circular import
    global background_task_manager
    background_task_manager = BackgroundTaskManager(shutdown_event)
    return background_task_manager


def get_background_task_manager():
    return background_task_manager


class BackgroundTaskManager:
    def __init__(self, shutdown_event):
        self.tasks = deque()
        self.running_tasks = set()
        self.task_available = asyncio.Event()
        self.shutdown_event = shutdown_event
        self.logger = util.Logger("background_tasks")

    def add(self, func, *args, **kwargs):
        self.tasks.append((func, args, kwargs))
        self.task_available.set()

    async def work(self):
        self.logger.info("Working")
        while True:
            tasks = [
                asyncio.create_task(self.task_available.wait()),
                asyncio.create_task(self.shutdown_event.wait()),
            ]

            await asyncio.wait(tasks, return_when="FIRST_COMPLETED")

            if self.shutdown_event.is_set():
                break

            self.logger.info("Running task")

            func, args, kwargs = self.tasks.popleft()

            task = asyncio.create_task(func(*args, **kwargs))

            self.running_tasks.add(task)

            task.add_done_callback(self.running_tasks.discard)

            if len(self.running_tasks) >= MAX_CONCURRENT_TASKS or not self.tasks:
                self.task_available.clear()

        self.close()

    async def close(self):
        self.logger.info("Gracefully shutting down")
        await asyncio.wait(self.running_tasks, timeout=5)
        for task in self.running_tasks:
            task.cancel()

        self.logger.info("Graceful shutdown complete")
