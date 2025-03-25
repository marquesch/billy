from sqlalchemy import Column
from sqlalchemy import DateTime
from sqlalchemy import Float
from sqlalchemy import ForeignKey
from sqlalchemy import Integer
from sqlalchemy import String
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


class Tenant(DeclarativeBaseModel):
    __tablename__ = "tenant"

    id = Column(Integer, primary_key=True)

    categories = relationship("Category", back_populates="tenant")
    bills = relationship("Bill", back_populates="tenant")
    users = relationship("User", back_populates="tenant")


class User(DeclarativeBaseModel):
    __tablename__ = "user"

    id = Column(Integer, primary_key=True)
    name = Column(String(80))
    tenant_id = Column(Integer, ForeignKey("tenant.id"))
    phone_number = Column(String(20))

    tenant = relationship("Tenant", back_populates="users")
