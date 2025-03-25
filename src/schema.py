from pydantic import BaseModel


class BasePayload(BaseModel):
    transaction_id: str


class MessagePayload(BasePayload):
    message_type: str
    message_body: str


class SendMessagePayload(MessagePayload):
    recipient_number: str
    quoted_message_id: str


class ReceiveMessagePayload(MessagePayload):
    sender_number: str
    message_id: str
    quoted_message_id: str
