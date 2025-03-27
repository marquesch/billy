from sqlalchemy import Boolean
from sqlalchemy import Column
from sqlalchemy import DateTime
from sqlalchemy import Float
from sqlalchemy import ForeignKey
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy import and_
from sqlalchemy import select
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.orm import relationship


class DeclarativeBaseModel(DeclarativeBase):
    pass


class Category(DeclarativeBaseModel):
    __tablename__ = "category"

    id = Column(Integer, primary_key=True, nullable=False)
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    tenant_id = Column(Integer, ForeignKey("tenant.id"), nullable=False)

    bills = relationship("Bill", back_populates="category")
    tenant = relationship("Tenant", back_populates="categories")

    @classmethod
    def get_all(cls, session, tenant_id):
        return session.execute(select(cls).where(cls.tenant_id == tenant_id)).scalars()

    def to_dict(self):
        return dict(id=self.id, name=self.name, description=self.description)


class Bill(DeclarativeBaseModel):
    __tablename__ = "bill"

    id = Column(Integer, primary_key=True)
    value = Column(Float, nullable=False)
    date = Column(DateTime, nullable=False)
    original_prompt = Column(String, nullable=True)
    category_id = Column(Integer, ForeignKey("category.id"), nullable=True)
    tenant_id = Column(Integer, ForeignKey("tenant.id"), nullable=False)
    message_id = Column(String, index=True, nullable=False)
    fake = Column(Boolean, nullable=False, default=False)

    category = relationship("Category", back_populates="bills")
    tenant = relationship("Tenant", back_populates="bills")

    @classmethod
    def get_many(cls, session, tenant_id, date=None, date_range=None, category_id=None):
        filters = [cls.tenant_id == tenant_id]

        if date is not None:
            filters.append(cls.date == date)

        elif date_range is not None:
            filters.append(cls.date.between(*date_range))

        if category_id is not None:
            filters.append(cls.category_id == category_id)

        return session.execute(select(cls).where(and_(*filters))).scalars()

    @classmethod
    def get_by_message_id(cls, session, tenant_id, message_id):
        return session.execute(
            select(cls).where(cls.message_id == message_id, cls.tenant_id == tenant_id)
        ).scalar_one_or_none()

    def to_basic_dict(self):
        return dict(
            value=self.value,
            date=self.date,
            category_id=self.category_id,
        )


class Tenant(DeclarativeBaseModel):
    __tablename__ = "tenant"

    id = Column(Integer, primary_key=True, nullable=False)

    users = relationship("User", back_populates="tenant")
    categories = relationship("Category", back_populates="tenant")
    bills = relationship("Bill", back_populates="tenant")


class User(DeclarativeBaseModel):
    __tablename__ = "user"

    id = Column(Integer, primary_key=True, nullable=False)
    name = Column(String(80), nullable=False)
    tenant_id = Column(Integer, ForeignKey("tenant.id"), nullable=False)
    phone_number = Column(String(20), nullable=False)
    tokens_per_hour = Column(Integer, nullable=False, default=999999999)
    generated_fake_bills = Column(Boolean, nullable=False, default=False)

    tenant = relationship("Tenant", back_populates="users")
