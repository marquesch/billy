from datetime import datetime
from typing import Optional

from billy.model import Bill
from billy.model import Category
from billy.model import Tenant
from billy.model import User

from sqlalchemy import delete
from sqlalchemy import func
from sqlalchemy import select
from sqlalchemy.orm import Session


class BaseRepository:
    def __init__(self, session: Session):
        self.session = session


class TenantBoundRepository(BaseRepository):
    def __init__(self, session: Session, tenant_id: int):
        super().__init__(session)
        self.tenant_id = tenant_id


class CategoryRepository(TenantBoundRepository):
    def create(self, name, description=None) -> Category:
        category = Category(
            name=name, description=description, tenant_id=self.tenant_id
        )
        self.session.add(category)
        self.session.commit()
        self.session.refresh(category)
        return category

    def get_by_id(self, category_id: int):
        return self.session.execute(
            select(Category).where(
                Category.id == category_id, Category.tenant_id == self.tenant_id
            )
        ).scalar_one_or_none()

    def get_by_name(self, name: str):
        return self.session.execute(
            select(Category).where(
                Category.name == name, Category.tenant_id == self.tenant_id
            )
        ).scalar_one_or_none()

    def get_all(self):
        return self.session.execute(select(Category)).scalars().all()


class BillRepository(TenantBoundRepository):
    def create(self, value, date, original_prompt, message_id, category_id, tenant_id):
        bill = Bill(
            value=value,
            date=date,
            original_prompt=original_prompt,
            message_id=message_id,
            category_id=category_id,
            tenant_id=tenant_id,
        )
        self.session.add(bill)
        self.session.commit()
        self.session.refresh(bill)
        return bill

    def get_by_id(self, bill_id: int):
        return self.session.execute(
            select(Bill).where(Bill.id == bill_id, Category.tenant_id == self.tenant_id)
        ).scalar_one_or_none()

    def get_all(self):
        return (
            self.session.execute(
                select(Bill).where(Category.tenant_id == self.tenant_id)
            )
            .scalars()
            .all()
        )

    def get_sum_by_date_range(
        self, from_: datetime, until: datetime, category_id: Optional[int] = None
    ):
        filters = [Bill.date.between(from_, until)]
        if category_id is not None:
            filters.append(Bill.category_id == category_id)

        result = self.session.execute(
            select(func.sum(Bill.value)).where(
                *filters, Category.tenant_id == self.tenant_id
            )
        ).scalar_one_or_none()

        return result if result is not None else 0.0

    def get_by_message_id(self, message_id):
        return self.session.execute(
            select(Bill).where(
                Bill.message_id == message_id, Bill.tenant_id == self.tenant_id
            )
        ).scalar_one_or_none()

    def delete(self, id):
        self.session.execute(
            delete(Bill).where(Bill.id == id, Bill.tenant_id == self.tenant_id)
        )
        self.session.commit()


class TenantRepository(BaseRepository):
    def create(self):
        tenant = Tenant()
        self.session.add(tenant)
        self.session.commit()
        self.session.refresh(tenant)
        return tenant

    def get_by_id(self, tenant_id: int):
        return self.session.execute(
            select(Tenant).where(Tenant.id == tenant_id)
        ).scalar_one_or_none()


class UserRepository(BaseRepository):
    def create(self, phone_number, tenant_id):
        user = User(phone_number=phone_number, tenant_id=tenant_id)
        self.session.add(user)
        self.session.commit()
        self.session.refresh(user)
        return user

    def get_by_id(self, user_id: int):
        return self.session.execute(
            select(User).where(User.id == user_id)
        ).scalar_one_or_none()

    def get_by_phone_number(self, phone_number: str):
        return self.session.execute(
            select(User).where(User.phone_number == phone_number)
        ).scalar_one_or_none()
