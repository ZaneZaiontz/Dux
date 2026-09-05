"""Database configuration for the Dux backend"""

import os


def connection_string() -> str:
    """Build the Postgres connection string from the environment

    Returns:
        A libpq connection string for the Dux database
    """
    user = os.environ.get("POSTGRES_USER", "dux")
    password = os.environ.get("POSTGRES_PASSWORD", "dux")
    host = os.environ.get("POSTGRES_HOST", "postgres")
    port = os.environ.get("POSTGRES_PORT", "5432")
    database = os.environ.get("POSTGRES_DB", "dux")
    return (
        f"postgresql://{user}:{password}@{host}:{port}/{database}"
        "?sslmode=disable"
    )
