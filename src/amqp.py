import aio_pika


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
