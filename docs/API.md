# Cineforge API Reference

Base URL: `<backend>/api/v1`. Interactive OpenAPI docs are always available at
`<backend>/docs` (Swagger) and `<backend>/redoc`.

Auth uses **JWT bearer tokens**. Obtain one via register/login, then send
`Authorization: Bearer <token>` on protected routes.

---

## Auth

### `POST /auth/register`
Create an account and receive a token.
```json
// request
{ "email": "you@example.com", "password": "min8chars", "full_name": "Ada" }
// 201 response
{ "access_token": "eyJ…", "token_type": "bearer", "user": { "id": "…", "email": "…", "full_name": "Ada", "is_active": true, "created_at": "…" } }
```
`409` if the email already exists.

### `POST /auth/login`
OAuth2 password flow — **form-encoded** (`application/x-www-form-urlencoded`), with the email
in the `username` field.
```
username=you@example.com&password=min8chars
```
Returns the same `Token` shape. `401` on bad credentials.

### `GET /auth/me`  🔒
Returns the current `User`.

---

## Jobs  🔒 (all require auth)

### `POST /jobs`
Create + enqueue a video generation job.
```json
// request
{ "script": "A boy walks through a rainy cyberpunk city…",
  "title": "Cyber Boy", "style": "cyberpunk", "aspect_ratio": "9:16" }
// 201 response (JobRead) — status is "queued"
```
`style` ∈ `cinematic_realistic | anime | cyberpunk | fantasy | portrait`.
`aspect_ratio` ∈ `16:9 | 9:16 | 1:1`.

### `GET /jobs?limit=50&offset=0`
List the caller's jobs, newest first (`JobRead[]`).

### `GET /jobs/{id}`
Full job (`JobDetail` = `JobRead` + `scenes[]` + `assets[]`). `404` if not owned.

### `POST /jobs/{id}/cancel`
Cooperative cancel — the worker stops between stages. `422` if already terminal.

### `POST /jobs/{id}/regenerate`
Re-enqueue a finished/failed job. `422` if still in progress.

### `PATCH /jobs/{id}/scenes/{scene_index}`
Partial scene edit (any subset of scene fields). Returns `JobDetail`. Pair with
`regenerate` to re-render with edits.

### `GET /jobs/{id}/stream`  — Server-Sent Events
Live progress. Emits a `snapshot` event (current durable state) immediately, then `progress`
events, closing on a terminal status.

```
event: snapshot
data: {"id":"…","status":"running","progress_pct":0,…}

event: progress
data: {"job_id":"…","status":"running","stage":"image_generation","pct":37.5,"message":"Rendering scene 2"}
```

> The browser `EventSource` API can't send an `Authorization` header, so the frontend reads
> this stream with `fetch` + a `ReadableStream` reader (see `useJobProgress`). Pass the bearer
> token as a normal header.

---

## Job lifecycle

```
pending → queued → running(stage,pct) → completed
                          │
                          ├─ retryable → queued (resume from manifest checkpoint)
                          └─ fatal     → failed (error + stage)
```

`current_stage` ∈ the 8 pipeline stages: `scene_generation, prompt_enhancement,
image_generation, character_lock, animation, voice, music, compose`.

When `status = completed`, `result_path` is a `/media/...` URL to the final MP4
(also listed among `assets`).

---

## Media

`GET /media/outputs/{job_id}/{filename}` — generated artifacts (final MP4, scene images,
audio). Served as static files by the backend; the frontend proxies `/media/*` to it.
