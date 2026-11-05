import pytest
from sqlalchemy import create_engine, select, Column, Integer, String
from sqlalchemy.orm import declarative_base, Session

from apps.backend.commerce.service import page, page_query
from apps.backend.platform.database import Problem

Base = declarative_base()

class Item(Base):
    __tablename__ = "items"
    id = Column(Integer, primary_key=True)
    name = Column(String)


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        for i in range(1, 46):
            session.add(Item(id=i, name=f"Item {i}"))
        session.commit()
        yield session
    engine.dispose()


def test_page_query_first_page(db_session):
    query = select(Item).order_by(Item.id)
    result = page_query(db_session, query, lambda x: x.name, limit=10)
    
    assert len(result["items"]) == 10
    assert result["items"][0] == "Item 1"
    assert result["items"][-1] == "Item 10"
    assert result["next_cursor"] is not None


def test_page_query_with_cursor(db_session):
    query = select(Item).order_by(Item.id)
    first_page = page_query(db_session, query, lambda x: x.name, limit=10)
    second_page = page_query(db_session, query, lambda x: x.name, limit=10, cursor=first_page["next_cursor"])
    
    assert len(second_page["items"]) == 10
    assert second_page["items"][0] == "Item 11"
    assert second_page["items"][-1] == "Item 20"
    assert second_page["next_cursor"] is not None


def test_page_query_last_page_no_next_cursor(db_session):
    query = select(Item).order_by(Item.id)
    # Total 45 items, limit 50 -> returns all 45 and next_cursor is None
    result = page_query(db_session, query, lambda x: x.name, limit=50)
    assert len(result["items"]) == 45
    assert result["next_cursor"] is None


def test_page_query_invalid_limit(db_session):
    query = select(Item).order_by(Item.id)
    with pytest.raises(Problem) as exc:
        page_query(db_session, query, lambda x: x.name, limit=0)
    assert exc.value.status == 422


def test_page_query_invalid_cursor(db_session):
    query = select(Item).order_by(Item.id)
    with pytest.raises(Problem) as exc:
        page_query(db_session, query, lambda x: x.name, cursor="invalid-cursor!")
    assert exc.value.status == 422
