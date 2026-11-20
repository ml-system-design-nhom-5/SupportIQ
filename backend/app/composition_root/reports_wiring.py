"""The wiring of reports: its stores, its use case, and its router (ARCH-21)."""

from fastapi import APIRouter
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.composition_root.accounts_wiring import AccountsWiring
from app.composition_root.shared_ports import SharedPorts
from app.platform.adapters.database import SqlAlchemyTransactionRunner
from app.reports import GetConsoleReport, ReportPorts, ReportStores
from app.reports.adapters.ai_figures import PostgresAiFigures
from app.reports.adapters.ticket_figures import PostgresTicketFigures
from app.reports.api.console_reports import (
    ConsoleReportRoutes,
    build_console_reports_router,
)


def build_report_stores(session: AsyncSession) -> ReportStores:
    """Build the stores of the report on one session, so every figure reads one transaction.

    Args:
        session: The session of the transaction.

    Returns:
        The stores.
    """
    return ReportStores(tickets=PostgresTicketFigures(session), ai=PostgresAiFigures(session))


def wire_reports(
    session_factory: async_sessionmaker[AsyncSession],
    shared: SharedPorts,
    accounts: AccountsWiring,
) -> APIRouter:
    """Create the report use case and its router.

    Args:
        session_factory: The session factory of the replicas.
        shared: The shared ports.
        accounts: The role checks and the session dependency.

    Returns:
        The router of `getConsoleReport`.
    """
    transactions = SqlAlchemyTransactionRunner(session_factory, build_report_stores)
    ports = ReportPorts(authorizer=accounts.authorizer, events=shared.events, steps=shared.steps)
    return build_console_reports_router(
        ConsoleReportRoutes(
            get_report=GetConsoleReport(transactions, ports),
            current_session=accounts.current_session,
        )
    )
