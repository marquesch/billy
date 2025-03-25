from enum import Enum

from src.cfg.database import SessionLocal
from src.libs.ai import IntentTypes
from src.libs.ai import get_user_intent
from src.model import Bill
from src.model import Category
from src.model import Tenant
from src.model import User
from src.util import create_whatsapp_aligned_text
from src.util import formatted_date

from main import get_bill_to_register
from main import get_category_to_register


class StepTypes(Enum):
    NONE = 0
    ASK_USER_NAME = 1
    ASK_USER_REGISTER_DEFAULT_CATEGORIES = 2


class Step:
    def __init__(self, session_info: dict, phone_number: str, logger):
        self.last_step_type = StepTypes(session_info.get("last_step_type", 0))
        self.session_info = session_info
        self.session = SessionLocal()
        self.phone_number = phone_number

        self.user: User | None = (
            self.session.query(User).where(User.phone_number == phone_number).first()
        )

        self.message: str | None = None

    async def process(self, message_body):
        match self.last_step_type:
            case StepTypes.NONE:
                if self.user is None:
                    self.logger.info("User is not registered. Starting registration")
                    return self._start_user_registration()

                self.logger.info("Checking user initial intent")

                return self.close()

            case StepTypes.ASK_USER_NAME:
                self.logger.info(
                    "Checking if user wants to register default categories"
                )
                return self._ask_if_user_wants_to_register_default_categories()

            case StepTypes.ASK_USER_REGISTER_DEFAULT_CATEGORIES:
                register_default_categories = message_body.lower() == "y"

                self.logger.info("Creating user")

                return self._create_user(register_default_categories)

    def close(self):
        self.session.close()
        return self

    async def _handle_user_initial_intent(self, message_body):
        user_intent = await get_user_intent(message_body)

        match user_intent:
            case IntentTypes.REGISTER_BILL:
                self.logger.info("Registering bill")

                bill = self._handle_bill_registration(message_body)

                self.message = create_whatsapp_aligned_text(
                    "*Bill created*",
                    {
                        "Value": bill.value,
                        "Category": bill.category.name,
                        "Date": formatted_date(bill.date),
                    },
                )

                self.session_info = dict()

                return self.close()

            case IntentTypes.REGISTER_CATEGORY:
                self.logger.info("Registering category")

                category = self._handle_category_registration(message_body)

                self.message = create_whatsapp_aligned_text(
                    "*Category created*",
                    {
                        "Name": category.name,
                        "Description": category.description,
                    },
                )

                self.session_info = dict()

                return self.close()

            case IntentTypes.DELETE_BILL:
                ...
                # TODO implement bill deletion flow

    async def _handle_bill_registration(self, message_body):
        categories = [
            category.to_dict()
            for category in Category.get_all(self.session, self.user.tenant_id)
        ]

        bill_to_register = await get_bill_to_register(message_body, categories)

        bill = Bill(
            value=bill_to_register["value"],
            date=bill_to_register["date"],  # FIXME will this date work?
            original_prompt=message_body,
            category_id=bill_to_register["category_id"],
            tenant_id=self.user.tenant_id,
        )

        self.session.add(bill)
        self.session.commit()
        self.session.refresh(bill)

        return bill

    async def _handle_category_registration(self, message_body):
        category_dict = await get_category_to_register(message_body)

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
        self.message = "Need to register. What's your name?"

        return self

    def _ask_if_user_wants_to_register_default_categories(self):
        self.last_step_type = StepTypes.ASK_USER_REGISTER_DEFAULT_CATEGORIES
        self.session_info = self.session_info | dict(
            last_step_type=self.last_step_type.value
        )

        self.message = "Do you want to register default categories? (y/n)"
        return self

    def _create_user(self, default_categories=False):
        tenant = Tenant()

        self.session.add(tenant)
        self.session.flush()
        self.session.refresh(tenant)

        categories = [Category(name="default", description="default category")]

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

        self.message = create_whatsapp_aligned_text(
            "User created",
            {
                "Name": user.name,
                "Phone number": user.phone_number,
                "Categories": [category.name for category in tenant.categories],
            },
        )

        self.session_info = dict()

        return self
