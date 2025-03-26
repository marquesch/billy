from enum import Enum

from src.cfg.database import SessionLocal
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


class StepTypes(Enum):
    NONE = 0
    ASK_USER_NAME = 1
    ASK_USER_REGISTER_DEFAULT_CATEGORIES = 2


class Step:
    def __init__(self, session_info: dict, message: ReceiveMessagePayload, logger):
        self.last_step_type = StepTypes(session_info.get("last_step_type", 0))
        self.session_info = session_info
        self.session = SessionLocal()
        self.logger = logger
        self.used_ai = False

        self.phone_number = message.sender_number
        self.message_body = message.message_body
        self.quoted_message_id = message.quoted_message_id
        self.message_id = message.message_id

        self.user: User | None = (
            self.session.query(User)
            .where(User.phone_number == self.phone_number)
            .first()
        )

        self.response: str | None = None

    async def process(self):
        match self.last_step_type:
            case StepTypes.NONE:
                if self.user is None:
                    self.logger.info("User is not registered. Starting registration")
                    return self._start_user_registration()

                self.logger.info("Checking user initial intent")

                return await self._handle_user_initial_intent()

            case StepTypes.ASK_USER_NAME:
                self.logger.info(
                    "Checking if user wants to register default categories"
                )
                return self._ask_if_user_wants_to_register_default_categories()

            case StepTypes.ASK_USER_REGISTER_DEFAULT_CATEGORIES:
                register_default_categories = self.message_body.lower() == "y"

                self.logger.info("Creating user")

                return self._create_user(register_default_categories)

    def close(self):
        self.session.commit()
        self.session.close()
        return self

    async def _handle_user_initial_intent(self):
        user_intent = await get_user_intent(self.message_body)

        self.used_ai = True

        match user_intent:
            case InitialIntentTypes.REGISTER_BILL:
                self.logger.info("Registering bill")

                bill = await self._handle_bill_registration()

                self.response = create_whatsapp_aligned_text(
                    "*Bill created*",
                    {
                        "Value": bill.value,
                        "Category": bill.category.name,
                        "Date": formatted_date(bill.date),
                    },
                )

                self.session_info = dict()

            case InitialIntentTypes.REGISTER_CATEGORY:
                self.logger.info("Registering category")

                category = await self._handle_category_registration()

                self.response = create_whatsapp_aligned_text(
                    "*Category created*",
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
                        "Please quote the message you sent"
                        "that created the bill you want to delete."
                    )

            case _:
                ...

        return self.close()

    def _handle_quoted_message_bill_deletion(self):
        bill_to_delete = Bill.get_by_message_id(
            self.session, self.user.tenant_id, self.quoted_message_id
        )

        self.response = create_whatsapp_aligned_text(
            "*Bill deleted*",
            {
                "Value": bill_to_delete.value,
                "Category": bill_to_delete.category.name,
                "Date": formatted_date(bill_to_delete.date),
            },
        )

        self.session.delete(bill_to_delete)
        self.session.commit()

    async def _handle_bill_registration(self):
        categories = [
            category.to_dict()
            for category in Category.get_all(self.session, self.user.tenant_id)
        ]

        bill_to_register = await get_bill_to_register(self.message_body, categories)

        bill = Bill(
            value=bill_to_register["value"],
            date=bill_to_register["date"],  # FIXME will this date work?
            original_prompt=self.message_body,
            category_id=bill_to_register["category_id"],
            tenant_id=self.user.tenant_id,
            message_id=self.quoted_message_id,
        )

        self.session.add(bill)
        self.session.commit()
        self.session.refresh(bill)

        return bill

    async def _handle_category_registration(self):
        category_dict = await get_category_to_register(self.message_body)

        category = Category(
            **category_dict,
            tenant_id=self.user.tenant_id,
        )

        self.session.add(category)
        self.session.commit()
        self.session.refresh(category)

        return category

    def _start_user_registration(self):
        self.last_step_type = StepTypes.ASK_USER_NAME
        self.session_info = dict(last_step_type=self.last_step_type.value)
        self.response = "Need to register. What's your name?"

        return self.close()

    def _ask_if_user_wants_to_register_default_categories(self):
        self.last_step_type = StepTypes.ASK_USER_REGISTER_DEFAULT_CATEGORIES
        self.session_info = self.session_info | dict(
            last_step_type=self.last_step_type.value, name=self.message_body
        )

        self.response = "Do you want to register default categories? (y/n)"
        return self.close()

    def _create_user(self, default_categories=False):
        tenant = Tenant()

        self.session.add(tenant)
        self.session.flush()
        self.session.refresh(tenant)

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

        self.session.add_all(categories)
        self.session.add(user)
        self.session.commit()
        self.session.refresh(user)

        self.response = create_whatsapp_aligned_text(
            "User created",
            {
                "Name": user.name,
                "Phone number": user.phone_number,
                "Categories": [category.name for category in tenant.categories],
            },
        )

        self.session_info = dict()

        return self.close()
