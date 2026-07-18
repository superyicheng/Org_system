# Final presentation checklist

## The day before

- Run `START_DEMO.cmd` once while internet access is available.
- Confirm <http://127.0.0.1:8000/health> returns `{"status":"ok"}`.
- Run `scripts/smoke-test.ps1`.
- Rehearse the demo twice under three minutes.
- Keep `demo-prompts.txt` open in a text editor for copy/paste backup.

## Ten minutes before presenting

- Close unrelated browser tabs and notifications.
- Run `START_DEMO.cmd`.
- Click **Reset Demo**.
- Confirm the top counter starts at zero blocked runs.
- Confirm the backend mode label is either **Live AI analysis** or **Backend mock fallback**—not local fallback if you intend to claim the API is live.

## If anything fails

- Backend/LLM failure: continue; the UI displays a transparent fallback label.
- Browser state is dirty: click **Reset Demo**.
- Terminal animation was interrupted: reset and repeat the new-hire flow.
- Never claim the simulated terminal created or blocked a real Kubernetes resource.

