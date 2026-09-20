# Sprint 01 Acceptance Result

## Environment

- Python: 3.14.5
- Runtime dependencies: none
- Scope: sayelf-pet-story-agent Build 0.1 / Sprint 01 only

## Checks run

### Contract and integration tests

Command:

```text
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -v
```

Result: **8 tests passed**.

Covered evidence:

- Session golden path and illegal transition protection.
- Job retry path and terminal-state protection.
- JSONL ledger append order and reload.
- Ledger has no update/delete mutation API.
- Mock provider contract.
- Fault provider failure and recovery under the same adapter contract.
- Pilot 01 golden path.
- Provider fault stops before a video is marked ready.

### User-facing demo

Command:

```text
$env:PYTHONPATH = "src"
python -m sayelf_pet_story_agent
```

Result:

```text
sayelf-pet-story-agent Pilot 01: READY
Event: Pet Expo Pilot 01
Campaign: My Pet Movie
Story shots: 8
Session: completed
Video: ready
Share: ready
Hall play: eligible
```

## Evidence boundary

This proves the local Sprint 01 contracts only. It does not prove real provider availability, media quality, Shot QA, Final Assembly, network resilience, concurrency, or live hall playback; those remain outside this sprint by design.

## WebUI smoke check

Command:

```text
python -m http.server 8080 --directory webui
```

Result: **passed** in the local browser preview.

Verified user path:

```text
Open → enter/default pet description → choose mode/ratio → Generate
→ progress state → completed state → 8-shot story result
```

The page is intentionally a local demo surface. It creates a deterministic local MP4 through the local renderer and does not claim to use a real AI video provider.

## Local video return and quota check

Verified against `python webui/server.py`:

- Text-only submission returned HTTP `201`, `returned_to_user: true`, a `video_url`, and a `download_url`.
- The returned video endpoint served HTTP `200` with `Content-Type: video/mp4`; download mode returned an attachment filename.
- A second successful submission for the same local visitor returned HTTP `429` with `DAILY_VIDEO_LIMIT`.
- A request containing three images returned HTTP `400`; the accepted maximum is two images.
- The response exposes only generation status, playback/download URLs, and quota counters; submitted text and image bytes are not echoed.

The local limit is a demo guard keyed by a browser-local visitor id. It is not production authentication or a cross-device identity system.

## Prompt board check

- Image count and video storyboard count both render as **8**.
- Each of the 8 image Prompt cards has an independent copy action.
- The video storyboard area has one aggregate copy action covering all 8 prompts in sequence.
- Local browser verification showed the image-copy and aggregate-copy confirmation messages.

## UI extension check

- SAYELF logo asset loads in the header from the local webui assets directory.
- Language toggle switches the page, status labels, storyboard names, image Prompts, video storyboard Prompts, modal labels, and copy controls between Chinese and English.
- QR entry and camera/photo entry controls are present; selected files remain browser-local.
- Model API entry opens a configuration modal. The local demo explicitly avoids saving or sending API keys and does not call an external service.
- Browser console check: no error or warning entries during the smoke flow.

## QR → Agent session bar check

- A local QR join simulation moves through `VERIFYING` to `CONNECTED` before revealing the session composer.
- Before connection, the photo entry and `01 / PET INTAKE` remain hidden; after `CONNECTED`, both are revealed as the next user step.
- The connected session panel only points to `01 / PET INTAKE`; there is no second message composer.
- `01 / PET INTAKE` accepts text-only, image-only, or image-plus-text as one combined pet input.
- The UI states that the current flow is local-only and does not send visitor content to an external Agent.
- Real connection is intentionally not claimed: the signed, expiring, one-time join-token and multipart message contract is documented in `SESSION_CONNECTION_CONTRACT.md`.

## Exhibitor QR manager check

- The standalone backend page is available at `/admin.html`; it contains generation, PNG/PDF download and status controls, and does not contain a “Scan to enter” action.
- The visitor page remains `/`; the backend and visitor responsibilities are separated.
- The QR manager loads the fixed Pilot 01 activity, exhibitor and booth choices.
- Generating a QR creates a signed local join URL, a PNG asset and a print-ready PDF asset.
- The manager displays `ACTIVE` status, expiry time, join URL and generated-history rows.
- PNG/PDF downloads are served by the local WebUI server; no QR generation service receives the event or booth data.
