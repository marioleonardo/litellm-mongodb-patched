import asyncio
import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException, Request, status
from prisma import errors as prisma_errors
from prisma.errors import (
    ClientNotConnectedError,
    DataError,
    ForeignKeyViolationError,
    HTTPClientClosedError,
    MissingRequiredValueError,
    PrismaError,
    RawQueryError,
    RecordNotFoundError,
    TableNotFoundError,
    UniqueViolationError,
)

sys.path.insert(
    0, os.path.abspath("../../..")
)  # Adds the parent directory to the system path

import litellm
from litellm._logging import verbose_proxy_logger
from litellm.proxy._types import ProxyErrorTypes, ProxyException
from litellm.proxy.db.exception_handler import PrismaDBExceptionHandler


# Test is_database_connection_error method
@pytest.mark.parametrize(
    "prisma_error",
    [
        HTTPClientClosedError(),
        ClientNotConnectedError(),
        PrismaError("can't reach database server"),
        PrismaError("connection refused"),
        PrismaError("timed out while connecting"),
    ],
)
def test_is_database_connection_error_prisma_connection_errors(prisma_error):
    """
    Test that only Prisma connection-related errors are considered DB connection errors.
    """
    assert PrismaDBExceptionHandler.is_database_connection_error(prisma_error) == True


@pytest.mark.parametrize(
    "prisma_error",
    [
        PrismaError(),
        PrismaError("validation failed on query"),
        DataError(data={"user_facing_error": {"meta": {"table": "test_table"}}}),
        UniqueViolationError(
            data={"user_facing_error": {"meta": {"table": "test_table"}}}
        ),
        ForeignKeyViolationError(
            data={"user_facing_error": {"meta": {"table": "test_table"}}}
        ),
        MissingRequiredValueError(
            data={"user_facing_error": {"meta": {"table": "test_table"}}}
        ),
        RawQueryError(data={"user_facing_error": {"meta": {"table": "test_table"}}}),
        TableNotFoundError(
            data={"user_facing_error": {"meta": {"table": "test_table"}}}
        ),
        RecordNotFoundError(
            data={"user_facing_error": {"meta": {"table": "test_table"}}}
        ),
    ],
)
def test_is_database_transport_error_non_connection_prisma_errors(prisma_error):
    """Data-layer errors should not trigger reconnect — DB is reachable when these occur."""
    assert PrismaDBExceptionHandler.is_database_transport_error(prisma_error) == False


def test_is_database_connection_generic_errors():
    """
    Test non-Prisma error cases for database connection checking
    """
    assert (
        PrismaDBExceptionHandler.is_database_connection_error(
            Exception("Regular error")
        )
        == False
    )

    # Test with ProxyException (DB connection)
    db_proxy_exception = ProxyException(
        message="DB Connection Error",
        type=ProxyErrorTypes.no_db_connection,
        param="test-param",
    )
    assert (
        PrismaDBExceptionHandler.is_database_connection_error(db_proxy_exception)
        == True
    )

    # Test with non-DB error
    regular_exception = Exception("Regular error")
    assert (
        PrismaDBExceptionHandler.is_database_connection_error(regular_exception)
        == False
    )


@pytest.mark.parametrize(
    "error",
    [
        ConnectionError("connection refused"),
        TimeoutError("timed out"),
        OSError("network is unreachable"),
        asyncio.TimeoutError(),
        HTTPClientClosedError(),
        ClientNotConnectedError(),
        PrismaError("can't reach database server"),
        PrismaError(),
    ],
)
def test_is_database_service_unavailable_error_infra_failures(error):
    """Infrastructure-level failures (socket/connection/timeout, prisma
    transport, unknown PrismaError) mean the DB could not answer, so auth
    must surface 503 instead of treating a valid key as invalid."""
    assert PrismaDBExceptionHandler.is_database_service_unavailable_error(error) is True


def test_is_database_service_unavailable_error_prisma_p1001_masquerades_as_dataerror():
    """Real-world regression: prisma-client-py raises the P1001 "can't reach
    database server" connectivity failure as a DataError (a data-layer type).
    A type-only check would miss it and return 401 during a genuine outage;
    the message keyword must still classify it as service-unavailable -> 503."""
    p1001_as_dataerror = DataError(
        data={
            "user_facing_error": {
                "message": "Can't reach database server at `127.0.0.1`:`5499`",
                "meta": {"table": "t"},
            }
        }
    )
    assert (
        PrismaDBExceptionHandler.is_database_service_unavailable_error(
            p1001_as_dataerror
        )
        is True
    )


def test_is_database_service_unavailable_error_cached_plan_escapes_as_503():
    """Composes with the cached-plan retry: when that recovery fails and the
    Postgres "cached plan must not change result type" error escapes (raised by
    prisma as a data-layer RawQueryError), it is a transient stale-DB-state
    condition, not an invalid key, so it must classify as service-unavailable
    -> 503 rather than fall through to 401."""
    cached_plan_error = RawQueryError(
        data={
            "user_facing_error": {
                "message": "cached plan must not change result type",
                "meta": {"table": "t"},
            }
        }
    )
    assert (
        PrismaDBExceptionHandler.is_database_service_unavailable_error(
            cached_plan_error
        )
        is True
    )


@pytest.mark.parametrize(
    "error",
    [
        DataError(data={"user_facing_error": {"meta": {"table": "t"}}}),
        UniqueViolationError(data={"user_facing_error": {"meta": {"table": "t"}}}),
        RecordNotFoundError(data={"user_facing_error": {"meta": {"table": "t"}}}),
        Exception("some unrelated error"),
        ValueError("bad value"),
    ],
)
def test_is_database_service_unavailable_error_excludes_non_infra(error):
    """Data-layer errors (the DB IS reachable and answered) and generic
    non-DB errors must NOT be classified as service-unavailable, otherwise a
    genuine 401 would be masked as a transient 503."""
    assert (
        PrismaDBExceptionHandler.is_database_service_unavailable_error(error) is False
    )


def test_is_database_service_unavailable_error_asyncpg(monkeypatch):
    """asyncpg connection/interface errors map to service-unavailable. asyncpg
    is not a hard dependency, so inject a stand-in module to exercise the
    branch deterministically regardless of the install environment."""
    import sys
    import types

    fake_asyncpg = types.ModuleType("asyncpg")
    fake_exceptions = types.ModuleType("asyncpg.exceptions")

    class PostgresConnectionError(Exception):
        pass

    class InterfaceError(Exception):
        pass

    class UniqueViolationError(Exception):  # data-layer, must stay False
        pass

    fake_exceptions.PostgresConnectionError = PostgresConnectionError
    fake_exceptions.InterfaceError = InterfaceError
    fake_exceptions.UniqueViolationError = UniqueViolationError
    fake_asyncpg.exceptions = fake_exceptions

    monkeypatch.setitem(sys.modules, "asyncpg", fake_asyncpg)
    monkeypatch.setitem(sys.modules, "asyncpg.exceptions", fake_exceptions)

    assert (
        PrismaDBExceptionHandler.is_database_service_unavailable_error(
            PostgresConnectionError("connection reset")
        )
        is True
    )
    assert (
        PrismaDBExceptionHandler.is_database_service_unavailable_error(
            InterfaceError("connection was closed")
        )
        is True
    )
    assert (
        PrismaDBExceptionHandler.is_database_service_unavailable_error(
            UniqueViolationError("duplicate key")
        )
        is False
    )


# Test should_allow_request_on_db_unavailable method
@patch(
    "litellm.proxy.proxy_server.general_settings",
    {"allow_requests_on_db_unavailable": True},
)
def test_should_allow_request_on_db_unavailable_true():
    assert PrismaDBExceptionHandler.should_allow_request_on_db_unavailable() == True


@patch(
    "litellm.proxy.proxy_server.general_settings",
    {"allow_requests_on_db_unavailable": False},
)
def test_should_allow_request_on_db_unavailable_false():
    assert PrismaDBExceptionHandler.should_allow_request_on_db_unavailable() == False


@patch(
    "litellm.proxy.proxy_server.general_settings",
    {"allow_requests_on_db_unavailable": True},
)
def test_handle_db_exception_with_connection_error():
    """
    Test that DB connection errors are handled gracefully when allow_requests_on_db_unavailable is True
    """
    db_error = ClientNotConnectedError()
    result = PrismaDBExceptionHandler.handle_db_exception(db_error)
    assert result is None


@patch(
    "litellm.proxy.proxy_server.general_settings",
    {"allow_requests_on_db_unavailable": False},
)
def test_handle_db_exception_raises_error():
    """
    Test that DB connection errors are raised when allow_requests_on_db_unavailable is False
    """
    db_error = ClientNotConnectedError()
    with pytest.raises(ClientNotConnectedError):
        PrismaDBExceptionHandler.handle_db_exception(db_error)


def test_handle_db_exception_with_non_db_error():
    """
    Test that non-DB errors are always raised regardless of allow_requests_on_db_unavailable setting
    """
    regular_error = litellm.BudgetExceededError(
        current_cost=10,
        max_budget=10,
    )
    with pytest.raises(litellm.BudgetExceededError):
        PrismaDBExceptionHandler.handle_db_exception(regular_error)
