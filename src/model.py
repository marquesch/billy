from src.util import formatted_date

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

    BASIC_CATEGORIES = {
        "Alimentação": "Gastos com supermercado, feiras, açougues, padarias e também refeições fora de casa (restaurantes, lanchonetes, delivery",
        "Transporte": "Custos com combustível, manutenção do veículo, seguro auto, IPVA, estacionamento, pedágios, transporte público (ônibus, metrô) e aplicativos de transporte",
        "Contas de Casa": "Despesas essenciais como energia elétrica, água, gás, internet, telefone fixo e planos de celular.",
        "Saúde": "Gastos com plano de saúde, consultas médicas e dentárias não cobertas, exames, medicamentos e farmácia em geral.",
        "Educação": "Mensalidades escolares ou de faculdade, cursos extras (idiomas, esportes), material escolar, livros e uniformes.",
        "Cuidados Pessoais": "Despesas com higiene pessoal, cosméticos, cabeleireiro, academia, roupas e calçados para os membros da família.",
        "Lazer e Entretenimento": "Gastos com cinema, teatro, shows, streaming (Netflix, Spotify, etc.), viagens curtas, hobbies, passeios, livros e revistas não relacionados à educação formal.",
        "Dívidas e Empréstimos": "Pagamento de parcelas de empréstimos pessoais, financiamentos e faturas de cartão de crédito.",
    }

    DEFAULT_CATEGORY = {
        "name": "Diversos",
        "description": "Gastos que não se encaixam em outras categorias",
    }

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
    tenant_id = Column(Integer, ForeignKey("tenant.id"), index=True, nullable=False)
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

    def to_dict(self):
        return dict(
            value=self.value,
            date=formatted_date(self.date),
            category_id=self.category_id,
        )


class Tenant(DeclarativeBaseModel):
    __tablename__ = "tenant"

    id = Column(Integer, primary_key=True, nullable=False)
    generated_fake_bills = Column(Boolean, nullable=False, default=False)

    users = relationship("User", back_populates="tenant")
    categories = relationship("Category", back_populates="tenant")
    bills = relationship("Bill", back_populates="tenant")

    @classmethod
    def get_by_id(cls, session, tenant_id):
        return session.execute(
            select(cls).where(cls.id == tenant_id)
        ).scalar_one_or_none()


class User(DeclarativeBaseModel):
    __tablename__ = "user_account"

    id = Column(Integer, primary_key=True, nullable=False)
    name = Column(String(80), nullable=False)
    tenant_id = Column(Integer, ForeignKey("tenant.id"), nullable=False)
    phone_number = Column(String(20), index=True, unique=True, nullable=False)
    tokens_per_hour = Column(Integer, nullable=False, default=20000)
    send_notification = Column(Boolean, nullable=False, default=True)
    last_version_notified = Column(Integer, nullable=True, default=0)

    tenant = relationship("Tenant", back_populates="users")
