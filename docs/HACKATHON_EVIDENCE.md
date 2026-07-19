# OpenAI Build Week — evidence pack

This file separates the old prototype from the Org_system work and gives judges an auditable path. It intentionally contains placeholders rather than fabricated Codex or model claims.

## Official rule requirements that matter here

The [Official Rules](https://openai.devpost.com/rules) define the Submission Period as **July 13, 2026, 9:00 AM PT through July 21, 2026, 5:00 PM PT**. A project must be newly created during that period or, if it existed before, meaningfully extended with Codex and/or GPT-5.6 after the start. Pre-existing projects must clearly distinguish old and new work and supply evidence of Codex/GPT-5.6 use during the period, such as timestamped Codex session logs, dated commits, or equivalent.

The rules also require a working project built with Codex/GPT-5.6, a public YouTube demo under three minutes with audio about how both were used, a repository, a README explaining the collaboration, and the `/feedback` Codex Session ID for the thread where most core functionality was built.

## Existing baseline versus this submission work

| Before this build | Org_system work to document |
|---|---|
| `6fa4f44` (July 17, 2026) was a Hive.skill platform-engineering prototype: Chroma retrieval, generated scripts, and one demo screen. | The current working tree replaces it with Org_system: generic experience lifecycle, consent/visibility, a PostgreSQL/SQLite memory store, verifier state transitions, authenticated Streamable HTTP MCP recall/store tools, Google identity, per-laptop revocable tokens, a gateway capture endpoint, three dashboards, and lifecycle tests. |

The core implementation was committed during the Submission Period:

```text
Commit: 7abbfa0b506803a22621ea774a89420ad85cc1eb
Timestamp: 2026-07-18T17:49:47-04:00
Message: Build Org_system verified experience loop
```

The shared cloud deployment extension was also committed during the Submission Period:

```text
Commit: 92f73ca5d59c4fa1c0e8a40f9a634eb94d928e54
Timestamp: 2026-07-19T02:33:16-04:00
Message: Add shared cloud Codex deployment
```

## Complete before submitting

1. In the **GPT-5.6 Codex project thread that contains the majority of this core work**, run `/feedback` and put the returned value here:

   ```text
   /feedback Session ID: REPLACE_WITH_REAL_SESSION_ID
   Session timestamp in PT: REPLACE_WITH_REAL_TIMESTAMP
   Codex surface and model shown in the session: REPLACE_WITH_EVIDENCE
   ```

2. Make and preserve a dated commit of the current Org_system files during the Submission Period. Do not rewrite prior history. Capture:

   ```bash
   git status
   git add README.md backend frontend docs scripts Hive.skill-demo.html
   git commit -m "Build Org_system verified experience loop"
   git log --date=iso-strict --format=fuller -1
   ```

3. In the Devpost description and README, link the commit and state the real Codex contributions: architecture translation, API/store/verifier/MCP implementation, dashboard construction, and testing. State the human decisions separately. Do not state that GPT-5.6 was used unless the session evidence confirms it.

4. Keep the public repo or grant both required addresses access: `testing@devpost.com` and `build-week-event@openai.com`. Record the commit URL here:

   ```text
   Core implementation commit: 7abbfa0b506803a22621ea774a89420ad85cc1eb
   Submission commit URL: REPLACE_WITH_URL
   Public demo video URL: REPLACE_WITH_URL
   ```

5. Record a short screen capture of `git log`, the `/feedback` result, capture → verify → recall, and the resulting attribution receipt. It is strong supporting evidence, but the official submission still needs the actual session ID and <3-minute public YouTube demo.

## Source of truth

This is a convenience checklist. If it differs from the [Official Rules](https://openai.devpost.com/rules), the rules control.
