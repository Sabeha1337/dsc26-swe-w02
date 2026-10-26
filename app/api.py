"""HTTP layer for the Tawseel parcel service.

The HTTP layer translates requests into calls to app.domain; the domain decides.
See README.md for the four operations, their operationIds and their errors.
"""

import secrets
import uuid

from fastapi import FastAPI, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.domain import EventType, InvalidTransition, Parcel, ParcelState, apply_event

PROBLEM_JSON = "application/problem+json"
MAX_COD_PIASTRES = 5_000_000


class ParcelCreate(BaseModel):
    """The request body accepted by POST /v1/parcels."""

    merchant_ref: str = Field(min_length=1, max_length=64)
    cod_amount_piastres: int = Field(ge=0, le=MAX_COD_PIASTRES)
    address_text: str = Field(min_length=1, max_length=500)


class ParcelOut(BaseModel):
    """The JSON representation of one parcel."""

    id: str
    merchant_ref: str
    cod_amount_piastres: int
    address_text: str
    state: ParcelState
    attempts: int


class ParcelPage(BaseModel):
    """One page returned by GET /v1/parcels."""

    items: list[ParcelOut]
    next_cursor: str | None


class EventIn(BaseModel):
    """The request body accepted by POST /v1/parcels/{parcel_id}/events."""

    type: EventType


class _Store:
    """Everything one app remembers: parcels, refs and cursors.

    A new _Store is created inside create_app(), so two apps never share data.
    """

    def __init__(self) -> None:
        self.parcels: dict[str, Parcel] = {}
        self.merchant_refs: set[str] = set()
        self.order: list[str] = []
        self.cursors: dict[str, int] = {}

    def new_id(self) -> str:
        return "pcl_" + uuid.uuid4().hex

    def issue_cursor(self, start_index: int) -> str:
        token = secrets.token_urlsafe(16)
        self.cursors[token] = start_index
        return token


def _problem(
    status_code: int,
    title: str,
    detail: str | None = None,
    errors: list[dict] | None = None,
) -> JSONResponse:
    """Build an RFC 9457 problem+json response."""
    body: dict = {
        "type": "about:blank",
        "title": title,
        "status": status_code,
    }
    if detail is not None:
        body["detail"] = detail
    if errors is not None:
        body["errors"] = errors
    return JSONResponse(
        status_code=status_code,
        content=body,
        media_type=PROBLEM_JSON,
    )


def _parcel_json(parcel: Parcel) -> dict:
    return {
        "id": parcel.id,
        "merchant_ref": parcel.merchant_ref,
        "cod_amount_piastres": parcel.cod_amount_piastres,
        "address_text": parcel.address_text,
        "state": parcel.state.value,
        "attempts": parcel.attempts,
    }


def create_app() -> FastAPI:
    """Return a NEW FastAPI app with its own empty in-memory store.

    Tests call this once per test, so nothing may be shared between two apps
    (no module-level dicts or counters for parcels).
    """
    app = FastAPI(title="Tawseel Parcel API", version="1.0.0")
    store = _Store()

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        # One entry per invalid field, including bad query parameters.
        errors = [
            {
                "loc": [str(part) for part in error.get("loc", ())],
                "msg": error.get("msg", "Invalid value"),
                "type": error.get("type", "value_error"),
            }
            for error in exc.errors()
        ]
        return _problem(
            422,
            "Validation Error",
            "Request validation failed",
            errors,
        )

    @app.post(
        "/v1/parcels",
        status_code=201,
        response_model=ParcelOut,
        operation_id="createParcel",
        responses={
            409: {"description": "merchant_ref already exists"},
            422: {"description": "Invalid request body"},
        },
    )
    def create_parcel(body: ParcelCreate, response: Response):
        if body.merchant_ref in store.merchant_refs:
            return _problem(
                409,
                "Conflict",
                f"merchant_ref already exists: {body.merchant_ref}",
            )

        parcel = Parcel(
            id=store.new_id(),
            merchant_ref=body.merchant_ref,
            cod_amount_piastres=body.cod_amount_piastres,
            address_text=body.address_text,
        )
        store.parcels[parcel.id] = parcel
        store.merchant_refs.add(parcel.merchant_ref)
        store.order.append(parcel.id)

        response.headers["Location"] = f"/v1/parcels/{parcel.id}"
        return _parcel_json(parcel)

    @app.get(
        "/v1/parcels/{parcel_id}",
        response_model=ParcelOut,
        operation_id="getParcel",
        responses={404: {"description": "Parcel not found"}},
    )
    def get_parcel(parcel_id: str):
        parcel = store.parcels.get(parcel_id)
        if parcel is None:
            return _problem(404, "Not Found", f"No parcel with id {parcel_id}")
        return _parcel_json(parcel)

    @app.get(
        "/v1/parcels",
        response_model=ParcelPage,
        operation_id="listParcels",
        responses={
            400: {"description": "Invalid cursor"},
            422: {"description": "Invalid state or limit"},
        },
    )
    def list_parcels(
        state: ParcelState | None = None,
        limit: int = Query(default=20, ge=1, le=100),
        cursor: str | None = None,
    ):
        if cursor is None:
            start = 0
        else:
            start = store.cursors.get(cursor)
            if start is None:
                return _problem(400, "Bad Request", "Invalid cursor")

        # Walk in creation order. A cursor stores a position in this order, so
        # items changing state between pages cannot cause skips or repeats.
        matches: list[tuple[int, Parcel]] = []
        for index in range(start, len(store.order)):
            parcel = store.parcels[store.order[index]]
            if state is None or parcel.state == state:
                matches.append((index, parcel))

        page = matches[:limit]
        next_cursor = None
        if len(matches) > limit:
            next_cursor = store.issue_cursor(matches[limit][0])

        return {
            "items": [_parcel_json(parcel) for _, parcel in page],
            "next_cursor": next_cursor,
        }

    @app.post(
        "/v1/parcels/{parcel_id}/events",
        response_model=ParcelOut,
        operation_id="recordParcelEvent",
        responses={
            404: {"description": "Parcel not found"},
            409: {"description": "Invalid transition"},
            422: {"description": "Unknown or missing event type"},
        },
    )
    def record_parcel_event(parcel_id: str, body: EventIn):
        parcel = store.parcels.get(parcel_id)
        if parcel is None:
            return _problem(404, "Not Found", f"No parcel with id {parcel_id}")

        try:
            updated = apply_event(parcel, body.type)
        except InvalidTransition as exc:
            return _problem(409, "Conflict", str(exc))

        store.parcels[parcel_id] = updated
        return _parcel_json(updated)

    return app


app = create_app()
