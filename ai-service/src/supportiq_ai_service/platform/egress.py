"""The third public entry point of platform: the egress allow-list and its one HTTP client.

The composition root creates the one client with `create_egress_client` (SEC-40), and the LLM
adapter tells a refusal of the allow-list apart from other failures with `EgressRefusedError`,
so it never retries one (ERR-12). Only adapters and the composition root import this module,
because it uses httpx.
"""

from supportiq_ai_service.platform.adapters.egress import (
    ALLOW_LIST_FILE_NAME,
    EgressAllowList,
    EgressAllowListInvalidError,
    EgressRefusedError,
    create_egress_client,
    packaged_egress_allow_list,
)

__all__ = [
    "ALLOW_LIST_FILE_NAME",
    "EgressAllowList",
    "EgressAllowListInvalidError",
    "EgressRefusedError",
    "create_egress_client",
    "packaged_egress_allow_list",
]
