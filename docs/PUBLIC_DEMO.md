# Public personal-memory trial

The public trial is a separate product surface for hackathon judges and visitors:

- URL: `https://org-system-demo-6hqysxhb3q-uk.a.run.app`
- Auth: Google sign-in, any Google account once the OAuth app is published
- Data: a dedicated `orgsystem_public` database, separate from the private organization service
- Privacy: every capture is forced to `private`; list, recall, dashboard, verification, replay, and MCP tools filter to the signed-in visitor
- MCP: a visitor can create and revoke a personal token from **Connect Codex**; it cannot access another visitor's memory

This is intentionally not a shared organizational workspace. The private deployment at `https://org-system-6hqysxhb3q-uk.a.run.app` remains allowlisted for the organization and has its own database credentials and Cloud Run service account.

## Required Google Auth Platform settings

In OAuth client `425968664012-87lb58gg2v04q0onj95q6vhojhg8qgda.apps.googleusercontent.com`, add this Authorized JavaScript origin exactly (no path and no trailing slash):

```text
https://org-system-demo-6hqysxhb3q-uk.a.run.app
```

Set the app's Audience to **External**, then publish it to **In production**. Testing mode is restricted to invited test accounts; production status is what allows public visitors. The application requests only basic Google identity information for browser sign-in.

## Visitor flow

1. Open the public-trial URL and sign in with Google.
2. Describe a completed task to save a private lesson, or ask about a planned task to recall prior lessons.
3. Open **Connect Codex** to create a personal remote MCP connection for that laptop.
4. Return to the same URL from another browser and sign in with the same Google account to see the same personal memory.

The Cloud Run health endpoint does not expose records. All application data routes require either the visitor's signed Google session or a per-visitor MCP bearer token.
