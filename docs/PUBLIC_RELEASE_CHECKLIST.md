# Public Release Checklist

Before publishing LiveFireTTX on GitHub:

- [ ] Confirm the license language with counsel.
- [x] Competing-use language updated to reference LiveFireTTX and substantially similar live-fire tabletop / exercise orchestration products.
- [ ] Review all generated scripts for safety.
- [x] Repository scanned for obvious secrets, tokens, private endpoints, local paths, generated artifacts, and unrelated internal project references.
- [ ] Confirm `livefirettx.db` and `generated/` are not committed.
- [ ] Run the app locally.
- [ ] Create a sample exercise.
- [ ] Trigger at least one narrative inject.
- [ ] Trigger at least one chaos script.
- [ ] Download the generated package.
- [ ] Deploy and destroy the generated Docker target.
- [ ] Tag the first release, for example `v0.1.0`.
- [ ] Add screenshots or demo video link to the README if desired.
