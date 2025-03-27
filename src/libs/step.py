from enum import Enum

from src.cfg.database import RedisClient
from src.libs.ai import InitialIntentTypes
from src.libs.ai import get_bill_to_register
from src.libs.ai import get_category_to_register
from src.libs.ai import get_user_intent
from src.model import Bill
from src.model import Category
from src.model import Tenant
from src.model import User
from src.schema import ReceiveMessagePayload
from src.util import create_whatsapp_aligned_text
from src.util import formatted_date

from sqlalchemy import select
from sqlalchemy.orm import Session


class StepTypes(Enum):
    NONE = 0
    ASK_USER_NAME = 1
    ASK_USER_REGISTER_DEFAULT_CATEGORIES = 2


class Step:
    def __init__(
        self,
        session_info: dict,
        message: ReceiveMessagePayload,
        db_session: Session,
        redis_client: RedisClient,
        logger,
    ):
        self.last_step_type = StepTypes(session_info.get("last_step_type", 0))
        self.session_info = session_info
        self.db_session = db_session
        self.redis_client = redis_client
        self.logger = logger
        self.used_ai = False

        self.phone_number = message.sender_number
        self.message_body = message.message_body
        self.quoted_message_id = message.quoted_message_id
        self.message_id = message.message_id

        self.user: User | None = self.db_session.execute(
            select(User).where(User.phone_number == self.phone_number)
        ).scalar_one_or_none()

        self.response: str | None = None
        self.tokens_used = 0

    async def process(self):
        match self.last_step_type:
            case StepTypes.NONE:
                if self.user is None:
                    self.logger.info("User is not registered. Starting registration")
                    return self._start_user_registration()

                self.logger.info("Checking user initial intent")

                time_to_wait = self._check_time_to_wait()

                if time_to_wait > 0:
                    self.response = (
                        f"You've reached the hourly token limit. "
                        f"Please wait at least {time_to_wait} seconds."
                    )  # TODO improve message

                    return self

                await self._handle_user_initial_intent()

                self._cache_token_usage()

                return self

            case StepTypes.ASK_USER_NAME:
                self.logger.info(
                    "Checking if user wants to register default categories"
                )
                return self._ask_if_user_wants_to_register_default_categories()

            case StepTypes.ASK_USER_REGISTER_DEFAULT_CATEGORIES:
                register_default_categories = self.message_body.lower() == "y"

                self.logger.info("Creating user")

                return self._create_user(register_default_categories)

    async def _handle_user_initial_intent(self):
        user_intent, tokens = await get_user_intent(self.message_body)
        self.tokens_used += tokens

        match user_intent:
            case InitialIntentTypes.REGISTER_BILL:
                self.logger.info("Registering bill")

                bill, tokens = await self._handle_bill_registration()
                self.tokens_used += tokens

                self.response = create_whatsapp_aligned_text(
                    "Bill created",
                    {
                        "Value": bill.value,
                        "Category": bill.category.name,
                        "Date": formatted_date(bill.date),
                    },
                )

                self.session_info = dict()

            case InitialIntentTypes.REGISTER_CATEGORY:
                self.logger.info("Registering category")

                category, tokens = await self._handle_category_registration()
                self.tokens_used += tokens

                self.response = create_whatsapp_aligned_text(
                    "Category created",
                    {
                        "Name": category.name,
                        "Description": category.description,
                    },
                )

                self.session_info = dict()

            case InitialIntentTypes.DELETE_BILL:
                self.logger.info("Gathering bills to delete")

                if self.quoted_message_id is not None:
                    self._handle_quoted_message_bill_deletion()

                else:
                    self.response = (
                        "Please quote the message you sent "
                        "that created the bill you want to delete."
                    )

            case InitialIntentTypes.UNKNOWN:
                self.response = (
                    "Sorry, I could not understand your message."  # TODO add usage text
                )

    def _handle_quoted_message_bill_deletion(self):
        bill_to_delete = Bill.get_by_message_id(
            self.db_session, self.user.tenant_id, self.quoted_message_id
        )

        self.response = "Bill already deleted."

        if bill_to_delete is not None:
            self.response = create_whatsapp_aligned_text(
                "Bill deleted",
                {
                    "Value": bill_to_delete.value,
                    "Category": bill_to_delete.category.name,
                    "Date": formatted_date(bill_to_delete.date),
                },
            )

            self.db_session.delete(bill_to_delete)
            self.db_session.commit()

    async def _handle_bill_registration(self):
        categories = [
            category.to_dict()
            for category in Category.get_all(self.db_session, self.user.tenant_id)
        ]

        bill_to_register, tokens = await get_bill_to_register(
            self.message_body, categories
        )

        bill = Bill(
            value=bill_to_register["value"],
            date=bill_to_register["date"],  # FIXME will this date work?
            original_prompt=self.message_body,
            category_id=bill_to_register["category_id"],
            tenant_id=self.user.tenant_id,
            message_id=self.message_id,
        )

        self.db_session.add(bill)
        self.db_session.commit()
        self.db_session.refresh(bill)

        return bill, tokens

    def _cache_token_usage(self):
        self.redis_client.set(
            f"{self.phone_number}:token_usage:{self.message_id}",
            self.tokens_used,
        )

    def _check_time_to_wait(self):
        tokens = self.redis_client.get_many(f"{self.phone_number}:token_usage:*")

        token_sum = sum(map(int, tokens))
        user_has_spare_tokens = token_sum < self.user.tokens_per_hour

        self.logger.info(
            f"User spent {token_sum} tokens out of {self.user.tokens_per_hour}"
        )

        if user_has_spare_tokens:
            return 0

        keys_ttl = self.redis_client.get_ttl(f"{self.phone_number}:token_usage:*")

        return min(keys_ttl)

    async def _handle_category_registration(self):
        category_dict, tokens = await get_category_to_register(self.message_body)

        category = Category(
            **category_dict,
            tenant_id=self.user.tenant_id,
        )

        self.db_session.add(category)
        self.db_session.commit()
        self.db_session.refresh(category)

        return category, tokens

    def _start_user_registration(self):
        self.last_step_type = StepTypes.ASK_USER_NAME
        self.session_info = dict(last_step_type=self.last_step_type.value)
        self.response = "Need to register. What's your name?"

        return self

    def _ask_if_user_wants_to_register_default_categories(self):
        self.last_step_type = StepTypes.ASK_USER_REGISTER_DEFAULT_CATEGORIES
        self.session_info = self.session_info | dict(
            last_step_type=self.last_step_type.value, name=self.message_body
        )

        self.response = "Do you want to register default categories? (y/n)"
        return self

    def _create_user(self, default_categories=False):
        tenant = Tenant()

        self.db_session.add(tenant)
        self.db_session.flush()
        self.db_session.refresh(tenant)

        categories = [
            Category(
                name="default", description="default category", tenant_id=tenant.id
            )
        ]

        if default_categories:
            categories.extend(
                [
                    Category(name=name, description=description, tenant_id=tenant.id)
                    for (name, description) in (
                        ("grocery", "Grocery related bills"),
                        ("subscriptions", "Monthly service subscriptions"),
                    )
                ]
            )

        user = User(
            name=self.session_info["name"],
            phone_number=self.phone_number,
            tenant_id=tenant.id,
        )

        self.db_session.add_all(categories)
        self.db_session.add(user)
        self.db_session.commit()
        self.db_session.refresh(user)

        self.response = create_whatsapp_aligned_text(
            "User created",
            {
                "Name": user.name,
                "Phone number": user.phone_number,
                "Categories": [category.name for category in tenant.categories],
            },
        )

        self.session_info = dict()

        return self
