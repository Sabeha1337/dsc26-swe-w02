# 1. Keep the parcel lifecycle in a pure module

## Status

Accepted

## Context

The parcel lifecycle (dispatch, deliver, fail, retry, return) is the part of the
service most likely to change as the business learns. The HTTP layer already has
framework concerns: routing, request validation, status codes and JSON. If the
rules lived inside the routes, every rule change would require an HTTP test, and
the same rules could not be reused by a background worker or a CLI.

Two other teams build against this contract, so the behaviour must be easy to
test and hard to break accidentally.

## Decision

We will keep all lifecycle rules in `app/domain.py` as pure Python. That module
imports no FastAPI, Starlette, Pydantic or SQLAlchemy. `apply_event(parcel, event)`
takes an immutable `Parcel`, returns a new `Parcel`, or raises `InvalidTransition`.
The HTTP layer only translates requests into calls to this function and maps the
result to a response.

## Consequences

It becomes easier to test the rules quickly, to reuse them outside HTTP, and to
change the framework without touching business logic. It becomes harder to put
everything in one place: the API layer needs a small translation step from domain
objects to JSON and from domain errors to HTTP status codes. Developers also have
to resist the temptation to add business logic inside route handlers.
