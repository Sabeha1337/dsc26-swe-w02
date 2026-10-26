# 2. Use cursor pagination for the parcel list

## Status

Accepted

## Context

`GET /v1/parcels` returns parcels in creation order and can be filtered by state.
Parcels change state while a client is paging: a client may fetch the first page
of `state=created`, dispatch those parcels, and then ask for the next page.

Offset pagination counts matching rows. When earlier rows leave the filtered set,
the count shifts and the next page can skip items or repeat them. The contract
requires that paging with a state filter never skips or repeats items, even when
earlier items change state between requests.

## Decision

We will use opaque cursor pagination keyed to each parcel's position in creation
order. The cursor is a random token that the server stores against the creation
index of the first item on the next page. Clients must send back exactly the
cursor they received; any other value is rejected with 400. `limit` defaults to
20 and must be between 1 and 100, and `next_cursor` is `null` on the last page.

## Consequences

It becomes easier to keep a stable walk while items change state, and the opaque
token hides the internal ordering from clients. It becomes harder to jump to an
arbitrary page, and the server must keep cursor state. In this in-memory version
cursors are lost on restart and are not shared between instances; a production
version would store them in a database or sign them, and would need a stable sort
key and a cleanup policy.
