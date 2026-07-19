# Final checklist

## Technical

- [x] All interface copy is English.
- [x] The original Tom, Sarah, and Mei accounts are preserved.
- [x] Both perspectives type natural-language input; no preset scenario buttons.
- [x] Mock mode completes the full offline demo.
- [x] Live OpenAI mode is available through environment variables.
- [x] Verified-only recall, consent, visibility, and attribution are tested.
- [x] Negative results can become verified reusable assets.
- [x] Metric verification fails closed.
- [x] Evidence replay runs in an independent process.
- [x] Codex-compatible stdio MCP entrypoint is included.
- [x] Ten automated tests pass, including semantic paraphrase recall and dynamic evidence replay.

## Before presenting

- [ ] Run `python -m unittest discover -s tests -v` from `backend`.
- [ ] Start the app and run `scripts/smoke-test.ps1`.
- [ ] Click **Reset demo** before recording.
- [ ] Keep `demo-prompts.txt` open for copy/paste backup.
- [ ] Use mock mode unless live model output is specifically required.
- [ ] Record the <3 minute public demo using `docs/DEMO_SCRIPT.md`.

## Submission evidence

- [ ] Make a dated Git commit within the Submission Period.
- [ ] Add the real `/feedback` Session ID; do not invent it.
- [ ] Confirm the exact Codex/model claim from session metadata.
- [ ] Add the public video URL and repository URL to the submission.
