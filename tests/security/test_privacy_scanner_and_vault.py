import uuid
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from src.modules.privacy.scanner import scan_and_mask_text, contains_unresolved_placeholder

def test_local_pii_scanner_rejects_unresolved_token_placeholders_without_vault():
    run_id = uuid.uuid4()
    raw = "Hi, I am Alice Nguyen, phone +1-415-555-0199, email alice@example.com, order ORD-998877, living at 742 Evergreen Terrace."
    res = scan_and_mask_text(raw, run_id=run_id)
    assert "Alice Nguyen" not in res.sanitized_text
    assert "415-555-0199" not in res.sanitized_text
    assert "alice@example.com" not in res.sanitized_text
    assert "ORD-998877" not in res.sanitized_text
    assert "742 Evergreen Terrace" not in res.sanitized_text
    assert contains_unresolved_placeholder(res.sanitized_text) is True
    assert contains_unresolved_placeholder("Your order will arrive tomorrow.") is False

@pytest.mark.asyncio
async def test_core_app_role_cannot_access_vault_schema(db_session: AsyncSession):
    with pytest.raises(Exception):
        await db_session.execute(text("SELECT * FROM vault.token_mappings"))
    await db_session.rollback()
