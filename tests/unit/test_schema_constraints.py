import pytest
from sqlalchemy import create_engine
from apps.backend.platform.models import Base, Ticket, Suggestion


def test_models_metadata_creates_cleanly_with_circular_fk():
    engine = create_engine("sqlite:///:memory:")
    # Should create all tables including Ticket -> Suggestion and Suggestion -> Ticket without error
    Base.metadata.create_all(engine)
    
    # Inspect foreign keys on tickets table
    from sqlalchemy import inspect
    inspector = inspect(engine)
    fks = inspector.get_foreign_keys("tickets")
    fk_targets = [fk["referred_table"] for fk in fks]
    assert "suggestions" in fk_targets or any(c.name == "current_suggestion_id" for c in Ticket.__table__.columns if c.foreign_keys)
    engine.dispose()
