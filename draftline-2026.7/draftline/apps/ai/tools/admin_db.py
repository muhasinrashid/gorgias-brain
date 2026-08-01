"""Admin database tools for Pydantic AI agents using the MCP postgres server.

This module provides admin-only access to the postgres database through the MCP alchemy server.
"""

import sys

from django.conf import settings
from pydantic_ai.mcp import MCPServerStdio

from apps.ai.permissions import tool_requires_superuser


def get_database_url():
    """Convert Django DATABASES setting back to a connection string."""
    db_config = settings.DATABASES["default"]

    engine = db_config["ENGINE"]
    name = db_config["NAME"]
    user = db_config["USER"]
    password = db_config["PASSWORD"]
    host = db_config["HOST"]
    port = db_config["PORT"]

    # Map Django engines to SQLAlchemy URL schemes. For postgres we force the
    # psycopg3 driver (`postgresql+psycopg`) so SQLAlchemy reuses the psycopg
    # we already ship for Django, instead of falling back to psycopg2.
    if "postgresql" in engine:
        scheme = "postgresql+psycopg"
    elif "mysql" in engine:
        scheme = "mysql"
    elif "sqlite" in engine:
        return f"sqlite:///{name}"
    else:
        scheme = "postgresql+psycopg"  # default fallback

    return f"{scheme}://{user}:{password}@{host}:{port}/{name}"


admin_db = MCPServerStdio(
    command=sys.executable,
    args=["-m", "mcp_alchemy.server"],
    env={
        "DB_URL": get_database_url(),
    },
    process_tool_call=tool_requires_superuser,
)
