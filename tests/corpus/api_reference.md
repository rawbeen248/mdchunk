# Widget API Reference

This document describes the REST API for managing widgets. All endpoints
require an API key passed via the `Authorization` header. Dr. Chen and J. R.
Alvarez co-authored the original spec. See Section 3.2.1 for rate limits.

## Authentication

Every request must include a bearer token.

```bash
curl https://api.example.com/v1/widgets \
  -H "Authorization: Bearer YOUR_API_KEY"
```

Tokens expire after 24 hours by default. Contact support at 9 a.m. UTC if
your token is revoked unexpectedly.

## Endpoints

### List widgets

`GET /v1/widgets`

Returns a paginated list of widgets.

#### Query parameters

| Name | Type | Required | Default | Notes |
|:---|:---:|:---:|---:|:---|
| `limit` | integer | No | 20 | Maximum 100 |
| `offset` | integer | No | 0 | Pagination offset |
| `status` | string | No | `active` | One of: `active`, `archived`, `deleted` |
| `sort` | string | No | `created_at` | One of: `created_at`, `updated_at`, `name` |

#### Example response

```json
{
  "widgets": [
    {"id": "w_123", "name": "Sprocket", "status": "active"},
    {"id": "w_124", "name": "Gadget", "status": "archived"}
  ],
  "next_offset": 20
}
```

### Create a widget

`POST /v1/widgets`

Required steps to create a widget:

1. Validate the payload against the schema
2. Reserve a unique `id`
3. Persist the record
   - write to the primary store
   - enqueue a replication event
4. Return the created resource

#### Request body

| Field | Type | Required |
|---|---|---|
| `name` | string | Yes |
| `tags` | array of string | No |
| `metadata` | object | No |

> Note: `metadata` values are stored as opaque JSON and are never indexed.
> Do not rely on querying by metadata fields.

### Delete a widget

`DELETE /v1/widgets/{id}`

Deletes a widget. This is a soft delete; the record moves to `status:
deleted` and is purged after 30 days.

## Error handling

All errors follow the same envelope:

```json
{"error": {"code": "not_found", "message": "Widget w_999 does not exist"}}
```

Common error codes:

- `not_found` — the resource does not exist
- `invalid_request` — the payload failed validation
- `rate_limited` — too many requests; back off and retry
  - respect the `Retry-After` header
  - use exponential backoff starting at 1s

## Changelog

### v2.3.0

Added the `sort` query parameter. Fixed a bug where `offset` beyond the
total count returned a 500 instead of an empty list.

### v2.2.0

Initial public release of the widgets endpoint.
