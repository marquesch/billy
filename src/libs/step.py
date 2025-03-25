from enum import Enum

from sqlalchemy.orm import Session
from src.cfg.database import SessionLocal
from src.model import Category
from src.model import Tenant
from src.model import User
from src.util import create_whatsapp_aligned_text


class StepTypes(Enum):
    NONE = 0
    ASK_USER_NAME = 1
    ASK_USER_REGISTER_DEFAULT_CATEGORIES = 2


class Step:
    def __init__(
        self,
        session_info: dict,
        phone_number: str,
        session: Session = SessionLocal(),
    ):
        self.last_step_type = StepTypes(session_info.get("last_step_type", 0))
        self.session_info = session_info
        self.session = session
        self.phone_number = phone_number

        self.user: User | None = (
            self.session.query(User).where(User.phone_number == phone_number).first()
        )

        self.message: str | None = None

    def process(self, message_body):
        match self.last_step_type:
            case StepTypes.NONE:
                if self.user is None:
                    self.last_step_type = StepTypes.ASK_USER_NAME
                    self.session_info = dict(last_step_type=self.last_step_type.value)
                    self.message = "Need to register. What's your name?"

                    return self

                self.last_step_type = StepTypes.NONE
                self.session_info = dict()
                self.message = "Done!"
                return self

            case StepTypes.ASK_USER_NAME:
                self.last_step_type = StepTypes.ASK_USER_REGISTER_DEFAULT_CATEGORIES
                self.session_info = self.session_info | dict(
                    name=message_body,
                    phone_number=self.phone_number,
                    last_step_type=self.last_step_type.value,
                )

                self.message = "Do you want to register default categories? (y/n)"

                return self

            case StepTypes.ASK_USER_REGISTER_DEFAULT_CATEGORIES:
                tenant = Tenant()

                self.session.add(tenant)
                self.session.flush()
                self.session.refresh(tenant)

                categories = [Category(name="default", description="default category")]

                register_default_categories = message_body.lower() == "y"

                if register_default_categories:
                    categories.extend(
                        [
                            Category(
                                name=name, description=description, tenant_id=tenant.id
                            )
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
