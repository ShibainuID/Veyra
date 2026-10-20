# VEYRA execution evidence (sandbox)

VEYRA is not on-chain. This is the operation log of a full run on the sandbox providers: the insurer is Sandbox Mutual and payments go through a sandbox ledger. No real money moved.

- **Run date:** 2026-10-20 (UTC), from commit `d92b816`
- **Story:** enroll Sari from the phone video, value her, upload her ownership document, insure her through the VEYRA agent, record a death incident, add the vet assessment, re-scan her muzzle, and submit the claim.
- **Totals:** 57 audit events, 3 sandbox receipts, 4 idempotency keys

## Files

| File | Contents |
| --- | --- |
| `audit-events.json` | Every audit event: actor, event, subject, and data such as payload hashes, idempotency keys, and receipts |
| `wallet.json` | The sandbox wallet balance and ledger (holds and debits) |
| `policies.json` | Policies with their insurer references and cover dates |
| `claims.json` | The claim with its checklist, identity check, and submission receipt |

## Sandbox receipts

- `SBX-APP-77E2CF359E`
- `SBX-CLM-5052BFABAB`
- `SBX-PAY-07D0626F3E`

## Controls shown in this run

- **The agent prepares, a person approves.** Every `action.proposed` event is followed by a separate human `action.approved` from the manager before any `action.executed`.
- **Approval binds the exact payload.** Each approval and execution records the same `payload_hash` and version.
- **Payment does not activate cover by itself.** The premium payment is executed first. The policy becomes active only on the insurer's own activation event.
- **Executions are idempotent.** Each execution carries an idempotency key, listed in `audit-events.json`.
- **A wrong-cow muzzle is blocked.** The identity checks record a mismatch for a different cow's muzzle before the matching scan.
- **A claim needs complete evidence.** The claim is submitted only after the vet assessment, the farmer declaration, and the identity check are on file.

## Event counts

| Event | Count |
| --- | --- |
| `action.approved` | 3 |
| `action.declined` | 1 |
| `action.executed` | 3 |
| `action.proposed` | 4 |
| `alert.created` | 1 |
| `animal.document_added` | 1 |
| `animal.registered` | 1 |
| `camera.gallery_published` | 1 |
| `camera.gallery_synced` | 3 |
| `camera.zone_scan` | 3 |
| `claim.declaration_confirmed` | 1 |
| `claim.drafted` | 1 |
| `claim.identity_checked` | 6 |
| `claim.submitted` | 1 |
| `enrollment.confirmed` | 1 |
| `enrollment.created` | 1 |
| `enrollment.processed` | 1 |
| `enrollment.processing_started` | 1 |
| `enrollment.video_uploaded` | 1 |
| `incident.alerts_linked` | 1 |
| `incident.finding_added` | 1 |
| `incident.recorded` | 1 |
| `policy.activated` | 1 |
| `replay.finished` | 3 |
| `replay.started` | 3 |
| `seed.animal_created` | 5 |
| `seed.policy_created` | 2 |
| `track.associated` | 4 |
| `valuation.confirmed` | 1 |

## Timeline

| Time (UTC) | Actor | Event | Result | Reference |
| --- | --- | --- | --- | --- |
| 13:18:46 | Demo seed (system) | seed.policy_created | active |  |
| 13:18:46 | Demo seed (system) | seed.animal_created |  |  |
| 13:18:46 | Demo seed (system) | seed.animal_created |  |  |
| 13:18:46 | Demo seed (system) | seed.policy_created | active |  |
| 13:18:46 | Demo seed (system) | seed.animal_created |  |  |
| 13:18:46 | Demo seed (system) | seed.animal_created |  |  |
| 13:18:46 | Demo seed (system) | seed.animal_created |  |  |
| 13:19:25 | W. Santoso (user) | enrollment.created |  |  |
| 13:19:25 | W. Santoso (user) | enrollment.video_uploaded |  |  |
| 13:19:25 | W. Santoso (user) | enrollment.processing_started |  |  |
| 13:20:14 | VEYRA worker (system) | enrollment.processed | review |  |
| 13:23:55 | W. Santoso (user) | enrollment.confirmed | register_new |  |
| 13:23:55 | W. Santoso (user) | animal.registered |  |  |
| 13:24:54 | W. Santoso (user) | valuation.confirmed |  |  |
| 13:24:56 | W. Santoso (user) | animal.document_added |  |  |
| 13:25:49 | W. Santoso (user) | camera.gallery_published |  |  |
| 13:25:49 | Camera worker (system) | camera.gallery_synced |  |  |
| 13:25:49 | Camera worker (system) | camera.gallery_synced |  |  |
| 13:25:49 | Camera worker (system) | camera.gallery_synced |  |  |
| 13:25:53 | W. Santoso (user) | replay.started |  |  |
| 13:25:54 | VEYRA (system) | camera.zone_scan | associated |  |
| 13:25:54 | VEYRA (system) | track.associated |  |  |
| 13:25:55 | VEYRA (system) | replay.finished |  |  |
| 13:26:19 | W. Santoso (user) | replay.started |  |  |
| 13:26:20 | VEYRA (system) | camera.zone_scan | associated |  |
| 13:26:20 | VEYRA (system) | track.associated |  |  |
| 13:26:21 | VEYRA (system) | replay.finished |  |  |
| 13:26:54 | W. Santoso (user) | replay.started |  |  |
| 13:26:54 | VEYRA (system) | camera.zone_scan | associated |  |
| 13:26:54 | VEYRA (system) | track.associated |  |  |
| 13:26:55 | VEYRA (system) | track.associated |  |  |
| 13:27:12 | VEYRA (system) | alert.created |  |  |
| 13:27:20 | VEYRA (system) | replay.finished |  |  |
| 13:32:45 | VEYRA agent (agent) | action.proposed · POLICY_APPLICATION |  |  |
| 13:36:50 | W. Santoso (user) | action.declined · POLICY_APPLICATION |  |  |
| 13:37:34 | VEYRA agent (agent) | action.proposed · POLICY_APPLICATION |  |  |
| 13:37:48 | W. Santoso (user) | action.approved · POLICY_APPLICATION |  |  |
| 13:37:48 | Sandbox Mutual (provider) | action.executed · POLICY_APPLICATION | succeeded | SBX-APP-77E2CF359E |
| 13:37:59 | VEYRA agent (agent) | action.proposed · PREMIUM_PAYMENT |  |  |
| 13:38:11 | W. Santoso (user) | action.approved · PREMIUM_PAYMENT |  |  |
| 13:38:11 | Sandbox payments (provider) | action.executed · PREMIUM_PAYMENT | succeeded | SBX-PAY-07D0626F3E |
| 13:38:11 | Sandbox Mutual (provider) | policy.activated |  |  |
| 13:42:54 | W. Santoso (user) | incident.recorded |  |  |
| 13:42:54 | VEYRA agent (agent) | incident.alerts_linked |  |  |
| 13:42:54 | W. Santoso (user) | claim.drafted |  |  |
| 13:44:22 | dr. R. Lestari (user) | incident.finding_added |  |  |
| 13:44:26 | W. Santoso (user) | claim.declaration_confirmed |  |  |
| 13:44:29 | W. Santoso (user) | claim.identity_checked | match |  |
| 13:45:07 | W. Santoso (user) | claim.identity_checked | mismatch |  |
| 13:45:12 | W. Santoso (user) | claim.identity_checked | mismatch |  |
| 13:45:17 | W. Santoso (user) | claim.identity_checked | match |  |
| 13:45:39 | W. Santoso (user) | claim.identity_checked | mismatch |  |
| 13:45:44 | W. Santoso (user) | claim.identity_checked | match |  |
| 13:46:28 | VEYRA agent (agent) | action.proposed · CLAIM_SUBMISSION |  |  |
| 13:46:52 | W. Santoso (user) | action.approved · CLAIM_SUBMISSION |  |  |
| 13:46:52 | Sandbox Mutual (provider) | action.executed · CLAIM_SUBMISSION | succeeded | SBX-CLM-5052BFABAB |
| 13:46:52 | Sandbox Mutual (provider) | claim.submitted |  | SBX-CLM-5052BFABAB |
