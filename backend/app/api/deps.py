from fastapi import Request

from app.services.orchestrator import Orchestrator


def get_orchestrator(request: Request) -> Orchestrator:
    return request.app.state.orchestrator


def get_trace_id(request: Request) -> str:
    return request.state.request_id
