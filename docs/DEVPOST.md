# org.system — submission write-up

**Tagline:** Shared memory for your team's AI — so nobody repeats the experiment a teammate
already proved doesn't work.

## Inspiration

_Written by the team._

## What it does

org.system is shared, verified memory that any AI client can reach over MCP.

Before costly work, the AI asks whether the team has already tried this. If a verified match
exists, it returns the result, the measured cost, the reusable next step, and an attribution
receipt naming the teammate who paid for the lesson. If nothing matches, it clears the work
as genuinely novel and suggests a bounded experiment rather than blocking innovation.

When work finishes, the AI captures what happened — including failures, with what they cost
— as a redacted, structured lesson. An administrator verifies the evidence before teammates
can rely on it. Similarity only nominates a candidate; consent, visibility, verification and
freshness decide whether another person's AI may actually use it.

Teams work inside organizations they create and join by invite. Memory is shared inside an
organization and never crosses between them.

## How we built it

The backend is FastAPI, serving both a web app and an authenticated Streamable HTTP MCP
endpoint, on SQLite locally and PostgreSQL on Cloud Run.

Retrieval is hybrid: lexical token overlap blended with local semantic vectors, weighted
0.35/0.65, with a similarity floor that fails closed. An honest "no match" is safer than
presenting an unrelated experience as precedent.

Every experience is validated against a JSON Schema and hashed with SHA-256, so a receipt
shown to a teammate is verifiable. Organizations, memberships and invite codes live in their
own tables, and `org_id` is a database column rather than a field inside the stored
experience, so moving or scoping a record never invalidates a hash someone has already seen.

Capture uses the OpenAI API to distil a raw work session into a structured lesson — task,
outcome, reusable next action, and measured resource evidence — with a deterministic
fallback so the system stays demonstrable without a key.

Connection is OAuth 2.1, implemented in the repo: dynamic client registration (RFC 7591),
PKCE with S256 only, refresh-token rotation, and protected-resource metadata (RFC 9728) so
any MCP client discovers and authenticates on its own. Identity comes from Google Sign-In,
and the access token carries the chosen organization for its entire life.

Finally, `AGENTS.md` and `CLAUDE.md` ship in the repository. MCP gives an AI the tools; these
files tell it when to use them.

## Challenges we ran into

_Written by the team. Factual raw material, if useful:_

- _OAuth discovery returned 401 pointing at a metadata URL that 404'd. The MCP SDK registers
  the metadata route on the sub-app mounted at `/mcp`, so it never appeared at the RFC 9728
  root. Starlette matches routes in registration order, so the fix was registering the
  well-known paths before `app.mount("/mcp", ...)`._
- _Replaying an authorization code is supposed to revoke every token it minted. The revocation
  and the raise shared one transaction, so raising rolled the revocation back and the tokens
  survived. Fixed by committing the revocation in its own transaction first._
- _Session capture initially verified a lesson only when the outcome was a success, which would
  have silently discarded every measured failure._
- _`required = true` makes a Codex session refuse to start without team memory, which also
  blocks anyone who has not authenticated yet._
- _Adding organizations to a live database had to give every existing record an owner without
  rewriting stored assets or invalidating a single SHA-256 receipt._

## Accomplishments that we're proud of

Connecting an AI client takes one command and one browser approval. There is no token to
generate, paste, store in an environment variable, or leak.

Failures are first-class. A measured dead end is stored as a dead end, with its cost, and
when it is later reused those saved GPU-hours or wet-lab days are credited on the impact
dashboard to the person who found it.

Cross-organization isolation is proven, not asserted. We have a test where one member's
verified lesson is invisible to another organization's recall, listings, and dashboards.

The full OAuth flow works end to end against the live service, and we verified it in a real
browser rather than only in tests: register a client, approve it, choose an organization, and
retrieve a teammate's verified receipt through MCP.

The whole suite is 43 tests covering lifecycle, permissions, organizations, OAuth grants,
public-trial isolation, session capture, and replay.

## What we learned

**An MCP server cannot "automatically" collect anything.** The protocol is client-pull; the
server only ever sees what the client chooses to send. There is no way to reach into an AI
session from the outside, and there should not be. What makes capture automatic is the
project instruction file telling the assistant to call the tool at task boundaries. The
instruction file turned out to matter as much as the server.

**Retrieval was the easy half.** Deciding whether one person's experience may be shown to
another — consent, visibility, verification status, freshness, organization — is where the
real design work lives. A shared memory that leaks is worse than no shared memory.

**Trust has to be designed in, or nobody turns it on.** "Shared team memory" sounds like
surveillance until you can show redaction, consent, administrator verification, and one-click
revocation. Every one of those constraints made the product easier to adopt, not harder.

**Verify against the real thing.** Several of our most confident beliefs were wrong until we
tested them: where OAuth metadata is served, which config values Codex accepts, and whether
Codex reads a repository-local config at all. Each one looked fine in theory and failed in
practice.

## What's next for org.system

Team-level visibility is the nearest gap. The schema promises `private`, `team` and `org`
scopes, but recall currently treats `team` and `org` the same, so a team-scoped lesson is
visible to the whole organization. Real sub-teams inside an organization are the next
structural change.

Distillation needs to get better. Without an API key the deterministic fallback classifies
outcomes with keyword heuristics, and it can mistake a carefully described failure for a
success. Outcome classification should never be guessed from keywords.

We also want richer impact accounting across more cost dimensions than GPU-hours and wet-lab
days, a scheduled re-verification pass that ages lessons out honestly as protocols drift, and
an organization interface that makes joining a team as simple as connecting a client already
is.

Longer term, the interesting question is what a team can attempt once its accumulated
experience is something every member's AI can reach. Coordination is what caps how large a
group can get before it starts repeating itself. We would like to move that ceiling.
