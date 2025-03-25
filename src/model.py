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

    id = Column(Integer, primary_key=True)
    name = Column(String)
    description = Column(String)
    tenant_id = Column(Integer, ForeignKey("tenant.id"))

    bills = relationship("Bill", back_populates="category")
    tenant = relationship("Tenant", back_populates="categories")

    @classmethod
    def get_all(cls, session, tenant_id):
        return (
            session.execute(select(cls).where(cls.tenant_id == tenant_id))
            .scalars()
            .all()
        )

    def to_dict(self):
        return dict(id=self.id, name=self.name, description=self.description)


class Bill(DeclarativeBaseModel):
    __tablename__ = "bill"

    id = Column(Integer, primary_key=True)
    value = Column(Float)
    date = Column(DateTime)
    original_prompt = Column(String)
    category_id = Column(Integer, ForeignKey("category.id"))
    tenant_id = Column(Integer, ForeignKey("tenant.id"))
    message_id = Column(String, index=True)

    category = relationship("Category", back_populates="bills")
    tenant = relationship("Tenant", back_populates="bills")

    @classmethod
    def get_many(cls, session, tenant_id, date=None, date_range=None, category=None):
        filters = [cls.tenant_id == tenant_id]

        if date is not None:
            filters.append(cls.date == date)

        elif date_range is not None:
            filters.append(cls.date.between(date_range))

        if category is not None:
            filters.append(cls.category_id == category)

        return session.execute(select(cls).where(and_(*filters))).scalars()


class Tenant(DeclarativeBaseModel):
    __tablename__ = "tenant"

    id = Column(Integer, primary_key=True)

    users = relationship("User", back_populates="tenant")


class User(DeclarativeBaseModel):
    __tablename__ = "user"

    id = Column(Integer, primary_key=True)
    name = Column(String(80))
    tenant_id = Column(Integer, ForeignKey("tenant.id"))
    phone_number = Column(String(20))

    tenant = relationship("Tenant", back_populates="users")
