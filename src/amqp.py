import os

import aio_pika

AMQP_HOST = os.getenv("AMQP_HOST", "rabbitmq")
AMQP_PORT = int(os.getenv("AMQP_PORT", 5672))
AMQP_USER = os.getenv("AMQP_USER", "billy")
AMQP_PASSWORD = os.getenv("AMQP_PASSWORD", "billy")

AMQP_RECEIVE_MESSAGE_QUEUE = "q.message.receive"
AMQP_SEND_MESSAGE_QUEUE = "q.message.send"


class AMQPClient:
    def __init__(self, **kwargs):
        self.connection_parameters = kwargs
        self.connection = None
        self.channel = None

    async def connect(self):
        self.connection = await aio_pika.connect_robust(**self.connection_parameters)
        self.channel = await self.connection.channel()

    async def close(self):
        await self.connection.close()

    async def publish(self, body, routing_key):
        await self.channel.default_exchange.publish(
            aio_pika.Message(body=body.encode()),
            routing_key=routing_key,
        )

    async def consume(self, queue_name, callback):
        queue = await self.channel.get_queue(queue_name)
        await queue.consume(callback)


amqp_client = AMQPClient(
    host=AMQP_HOST, port=AMQP_PORT, login=AMQP_USER, password=AMQP_PASSWORD
)


async def connect_amqp_client():
    await amqp_client.connect()
