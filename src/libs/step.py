from datetime import datetime
from datetime import timedelta
from enum import Enum
import random

from src.cfg.database import RedisClient
from src.libs.ai import InitialIntentTypes
from src.libs.ai import get_analyze_expense_trend
from src.libs.ai import get_bill_to_register
from src.libs.ai import get_bills_query_data
from src.libs.ai import get_category_to_register
from src.libs.ai import get_user_intent
from src.libs.ai import get_yes_or_no_answer
from src.model import Bill
from src.model import Category
from src.model import Tenant
from src.model import User
from src.schema import ReceiveMessagePayload
from src.util import create_whatsapp_aligned_text
from src.util import formatted_date

from sqlalchemy import and_
from sqlalchemy import delete
from sqlalchemy import func
from sqlalchemy import select
from sqlalchemy.orm import Session


class StepTypes(Enum):
    NONE = 0
    ASK_USER_NAME = 1
    ASK_USER_REGISTER_DEFAULT_CATEGORIES = 2
    ASK_USER_REGISTER_FAKE_BILLS = 3


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
                self.last_step_type = StepTypes.ASK_USER_REGISTER_DEFAULT_CATEGORIES

                self.logger.info(
                    "Checking if user wants to register default categories"
                )

                self.session_info = self.session_info | dict(
                    last_step_type=self.last_step_type.value, name=self.message_body
                )

                self.response = "Do you want to register default categories?"
                return self

            case StepTypes.ASK_USER_REGISTER_DEFAULT_CATEGORIES:
                self.last_step_type = StepTypes.ASK_USER_REGISTER_FAKE_BILLS

                register_default_categories, tokens = await get_yes_or_no_answer(
                    self.message_body
                )
                self.tokens_used += tokens

                self.logger.info("Checking if user wants to register fake bills.")

                self.session_info = self.session_info | dict(
                    register_default_categories=register_default_categories,
                    last_step_type=self.last_step_type.value,
                )

                self.response = "Should I register fake bills?"

                return self

            case StepTypes.ASK_USER_REGISTER_FAKE_BILLS:
                register_fake_bills, tokens = await get_yes_or_no_answer(
                    self.message_body
                )
                self.tokens_used += tokens

                register_default_categories = self.session_info.get(
                    "register_default_categories", False
                )

                self.user = self._create_user(register_default_categories)

                title = "*Registration complete*"

                if register_fake_bills:
                    self.logger.info("Registering fake bills")

                    total = self._handle_fake_bills_registration()

                    title = f"*Registration complete with {total} fake bills*"

                self.response = create_whatsapp_aligned_text(
                    title,
                    {
                        "Name": self.user.name,
                        "Phone number": self.user.phone_number,
                        "Max tokens per hour": self.user.tokens_per_hour,
                    },
                )

                return self

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
                self.logger.info("Gathering bill to delete")

                if self.quoted_message_id is not None:
                    self._handle_quoted_message_bill_deletion()

                else:
                    self.response = (
                        "Please quote the message you sent "
                        "that created the bill you want to delete."
                    )

            case InitialIntentTypes.SUM_BILLS:
                self.logger.info("Gathering bills to sum")

                sum, bills, tokens = await self._handle_bills_to_sum()
                self.tokens_used += tokens

                self.response = f"Sum of the bills: {sum}"

                if bills is not None:
                    bills_response = [
                        {
                            "Value": bill.value,
                            "Category": bill.category.name,
                            "Date": formatted_date(bill.date),
                        }
                        for bill in bills
                    ]

                    self.response = create_whatsapp_aligned_text(
                        f"Sum of the bills: {sum}", bills_response
                    )

            case InitialIntentTypes.REGISTER_FAKE_BILLS:
                self.logger.info("Registering fake bills")

                if self.user.generated_fake_bills:
                    self.response = "You have already generated fake bills"
                    return

                total = self._handle_fake_bills_registration()

                self.response = f"Created {total} fake bills"

            case InitialIntentTypes.DELETE_FAKE_BILLS:
                self.logger.info("Deleting fake bills")

                count = self.db_session.execute(
                    delete(Bill).where(
                        and_(Bill.tenant_id == self.user.tenant_id, Bill.fake.is_(True))
                    )
                ).rowcount

                self.response = f"Deleted {count} fake bills"

            case InitialIntentTypes.ANALYZE_EXPENSE_TREND:
                self.logger.info("Analyzing expense trend")

                categories = [
                    category.to_dict()
                    for category in Category.get_all(
                        self.db_session, self.user.tenant_id
                    ).all()
                ]

                bills, tokens = await self._handle_bills_to_analyze(categories)
                self.tokens_used += tokens

                bills_to_analyze = [bill.to_basic_dict() for bill in bills]

                analysis, tokens = await get_analyze_expense_trend(
                    bills_to_analyze, categories
                )
                self.tokens_used += tokens

                self.response = analysis

            case InitialIntentTypes.UNKNOWN:
                self.response = (
                    "Sorry, I could not understand your message."  # TODO add usage text
                )

    async def _handle_bills_to_analyze(self, categories):
        query_data, tokens = await get_bills_query_data(self.message_body, categories)

        if len(query_data["range"]) == 1:
            dates = dict(date=query_data["range"][0])

        else:
            dates = dict(date_range=query_data["range"])

        category_id = query_data.get("category_id", None)

        bills = Bill.get_many(
            session=self.db_session,
            tenant_id=self.user.tenant_id,
            category_id=category_id,
            **dates,
        )

        return bills, tokens

    def _handle_fake_bills_registration(self):
        categories = Category.get_all(self.db_session, self.user.tenant_id).all()

        total = 0
        bills = []
        for i in range(365):
            for _ in range(random.randint(1, 3)):
                total += 1
                category = random.choice(categories)
                value = random.randint(1, 1000)
                date = datetime.now() - timedelta(days=i)

                bill = Bill(
                    value=value,
                    date=date,
                    original_prompt=self.message_body,
                    category_id=category.id,
                    tenant_id=self.user.tenant_id,
                    message_id=self.message_id,
                    fake=True,
                )

                bills.append(bill)

        self.user.generated_fake_bills = True

        self.db_session.add_all(bills)
        self.db_session.commit()

        return total

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

    async def _handle_bills_to_sum(self):
        categories = [
            category.to_dict()
            for category in Category.get_all(self.db_session, self.user.tenant_id).all()
        ]

        query_data, tokens = await get_bills_query_data(self.message_body, categories)

        filters = [Bill.tenant_id == self.user.tenant_id]

        if len(query_data["range"]) == 1:
            filters.append(Bill.date == query_data["range"][0])
            dates = dict(date=query_data["range"][0])

        else:
            filters.append(Bill.date.between(*query_data["range"]))
            dates = dict(date_range=query_data["range"])

        if category_id := query_data.get("category_id", None):
            filters.append(Bill.category_id == category_id)

        sum = self.db_session.execute(
            select(func.sum(Bill.value)).where(and_(*filters))
        ).scalar()

        bills = None

        if query_data["show_bills"]:
            bills = Bill.get_many(
                session=self.db_session,
                tenant_id=self.user.tenant_id,
                category_id=category_id,
                **dates,
            )

        return sum, bills, tokens

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

        return user

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
