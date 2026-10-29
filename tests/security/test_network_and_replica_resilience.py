from pathlib import Path
import yaml

def test_compose_enforces_two_api_replicas_and_internal_worker_network():
    compose = yaml.safe_load(Path("infra/compose/docker-compose.yml").read_text(encoding="utf-8"))
    services = compose["services"]
    assert "core-api-1" in services and "core-api-2" in services
    assert "ai-worker" in services
    assert "pii-resolver" in services
    assert "egress-proxy" in services

    # Worker must not receive VAULT_DB_URL
    worker_env = services["ai-worker"].get("environment", {})
    assert "VAULT_DB_URL" not in worker_env
    assert "VAULT_DB_URL" in services["pii-resolver"].get("environment", {})

    # Core internal network must be marked internal: true so worker cannot bypass egress-proxy
    assert compose["networks"]["core_net"]["internal"] is True
