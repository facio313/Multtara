# Security Policy

## Supported versions

Security fixes are applied to the current `main` release and the active `dev`
integration branch. Development-tool branches are not production releases.

## Reporting a vulnerability

Do not open a public issue containing exploit details, credentials, personal
data, or a working proof of concept. Use GitHub's private vulnerability report
for this repository:

https://github.com/facio313/Multtara/security/advisories/new

Include the affected commit or release, the exposed surface, reproduction
steps, impact, and any suggested mitigation. Do not access data that is not
yours, degrade provider services, or test against the public production origin
without prior authorization.

Maintainers should acknowledge a report within five business days, provide a
sanitized status update at least every seven days while the report is open,
and coordinate disclosure after a fix or mitigation is available.

## Credential exposure

If a server credential is exposed, rotate it at the issuing provider before
removing it from active configuration. Treat repository cleanup and credential
revocation as separate operations. Public browser keys such as the Kakao Maps
JavaScript key must still be restricted to approved domains.

## Safety-data incidents

Incorrect closure, evacuation, water-quality, lightning, or access information
is a safety incident even when no software vulnerability is involved. Disable
the affected recommendation path, preserve the evidence and ingestion audit
records, and fall back to `UNKNOWN` until the authoritative source is restored
and the mapping is revalidated.
