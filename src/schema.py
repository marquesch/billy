from typing import Optional

from pydantic import BaseModel
from pydantic import field_validator


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
    quoted_message_id: Optional[str] = None

    @field_validator("quoted_message_id")
    @classmethod
    def validate_quoted_message_id(cls, v):
        if v == "":
            return None
        return v
