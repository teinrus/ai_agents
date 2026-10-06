"""Четыре ресурса контракта. Роут инструмент не вызывает."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from ai_department.api.schemas import (
    ConfirmationIn,
    MessageIn,
    RunOut,
    TaskCreated,
    TaskIn,
    ThreadCreated,
    ThreadOut,
)
from ai_department.api.service import (
    RunApi,
    ThreadApi,
    event_payloads,
    run_payload,
    thread_payload,
)
from ai_department.domain.errors import (
    ConfirmationError,
    RunNotFound,
    ThreadNotFound,
    ValidationError,
)


def build_router() -> APIRouter:
    """Собирает маршруты без знания ролей."""
    router = APIRouter()

    @router.post("/tasks", status_code=201, response_model=TaskCreated)
    def create_task(body: TaskIn, request: Request) -> TaskCreated:
        try:
            snapshot = _api(request).create_task(
                goal=body.goal,
                payload=body.payload,
                correlation_id=body.correlation_id,
                max_steps=None if body.constraints is None else body.constraints.max_steps,
                max_revisions=None if body.constraints is None else body.constraints.max_revisions,
                deadline=None if body.constraints is None else body.constraints.deadline,
            )
        except ValidationError as exc:
            raise HTTPException(
                status_code=422,
                detail={"kind": "validation", "message": exc.message},
            ) from exc
        return TaskCreated(run_id=snapshot.run_id, correlation_id=snapshot.correlation_id)

    @router.get("/runs/{run_id}", response_model=RunOut)
    def read_run(run_id: str, request: Request) -> RunOut:
        try:
            snapshot = _api(request).get_run(run_id)
        except RunNotFound as exc:
            raise HTTPException(
                status_code=404, detail={"kind": "not_found", "message": str(exc)}
            ) from exc
        return RunOut.model_validate(run_payload(snapshot))

    @router.get("/runs/{run_id}/events")
    def read_events(run_id: str, request: Request) -> list[dict[str, object]]:
        try:
            events = _api(request).get_events(run_id)
        except RunNotFound as exc:
            raise HTTPException(
                status_code=404, detail={"kind": "not_found", "message": str(exc)}
            ) from exc
        return event_payloads(events)

    @router.post("/runs/{run_id}/confirmations", response_model=RunOut)
    def answer_confirmation(run_id: str, body: ConfirmationIn, request: Request) -> RunOut:
        try:
            snapshot = _api(request).confirm(run_id, body.confirmation_id, body.decision)
        except RunNotFound as exc:
            raise HTTPException(
                status_code=404, detail={"kind": "not_found", "message": str(exc)}
            ) from exc
        except ConfirmationError as exc:
            raise HTTPException(
                status_code=409,
                detail={"kind": "confirmation", "message": exc.message},
            ) from exc
        return RunOut.model_validate(run_payload(snapshot))

    @router.post("/threads", status_code=201, response_model=ThreadCreated)
    def open_thread(request: Request) -> ThreadCreated:
        snapshot = _threads(request).open()
        return ThreadCreated(thread_id=snapshot.thread_id)

    @router.get("/threads/{thread_id}", response_model=ThreadOut)
    def read_thread(thread_id: str, request: Request) -> ThreadOut:
        try:
            snapshot = _threads(request).get_thread(thread_id)
        except ThreadNotFound as exc:
            raise _thread_missing(exc) from exc
        return ThreadOut.model_validate(thread_payload(snapshot))

    @router.post("/threads/{thread_id}/messages", response_model=ThreadOut)
    def post_message(thread_id: str, body: MessageIn, request: Request) -> ThreadOut:
        try:
            snapshot = _threads(request).say(thread_id, body.text)
        except ThreadNotFound as exc:
            raise _thread_missing(exc) from exc
        return ThreadOut.model_validate(thread_payload(snapshot))

    @router.post("/threads/{thread_id}/confirmations", response_model=ThreadOut)
    def answer_thread_confirmation(
        thread_id: str, body: ConfirmationIn, request: Request
    ) -> ThreadOut:
        try:
            snapshot = _threads(request).confirm(thread_id, body.confirmation_id, body.decision)
        except ThreadNotFound as exc:
            raise _thread_missing(exc) from exc
        except ConfirmationError as exc:
            raise HTTPException(
                status_code=409,
                detail={"kind": "confirmation", "message": exc.message},
            ) from exc
        return ThreadOut.model_validate(thread_payload(snapshot))

    @router.get("/threads/{thread_id}/events")
    def read_thread_events(thread_id: str, request: Request) -> list[dict[str, object]]:
        try:
            events = _threads(request).get_events(thread_id)
        except ThreadNotFound as exc:
            raise _thread_missing(exc) from exc
        return event_payloads(events)

    return router


def _api(request: Request) -> RunApi:
    api = getattr(request.app.state, "api", None)
    if not isinstance(api, RunApi):
        raise HTTPException(status_code=500, detail={"kind": "runtime", "message": "API не собран"})
    return api


def _threads(request: Request) -> ThreadApi:
    api = getattr(request.app.state, "threads", None)
    if not isinstance(api, ThreadApi):
        raise HTTPException(
            status_code=500, detail={"kind": "runtime", "message": "Приёмная не собрана"}
        )
    return api


def _thread_missing(exc: ThreadNotFound) -> HTTPException:
    return HTTPException(status_code=404, detail={"kind": "not_found", "message": str(exc)})
