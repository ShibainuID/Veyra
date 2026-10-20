# MVP assumptions

- **Monitoring: live observations are ingested, not movement-assessed.** Observations posted to
  `POST /api/v1/cameras/{id}/observations` (service token) go through the same identity-association rules as a
  replay and update tracks and last-seen, but the movement rule (`reduced_movement`, `observation_quality`) only runs
  inside camera replays (`POST /api/v1/demo/replays/{scenario}/start`), where windows close on scenario time.
- **Monitoring: replays are recorded footage ending by now.** A replay's observation time is
  `anchor + t`, with the anchor set so no observation is stamped after it is ingested (`anchor_at` on the replay).
- **Monitoring: a live track key silent for more than 30 s starts a new, unassigned track**, so a reused key never
  carries an earlier animal's identity.
