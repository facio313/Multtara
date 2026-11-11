# Main/dev migration — 2026-11-12

The user replaced tool/feature and retired-dev rules with two active branches: `main` is production and `dev` is development. Fetch `origin/main` before changes, validate on `dev`, and publish/deploy only reviewed main history. Local apps run only from the actual dev checkout through `scripts/dev-only.sh`; setting PORTFOLIO_BRANCH cannot bypass this checkout guard. The canonical resolver permits only main/sso and dev/local.

Pre-migration refs were saved in a verified Git bundle under `~/.local/share/cks-main-dev-migration/2026-11-12/Multtara/before-migration.bundle`. Original dirty/untracked/ignored files and worktrees are preserved. Existing branches are not deleted in this change. CI on dev must not publish or deploy production artifacts.

The cursor QA commit 96248d6 is integrated normally. Dependency-bot proposals remain archived in the verified bundle, without activating unreviewed major version upgrades.

Validation completed:

- 229 backend config/conditions/forecasts/trips tests passed with disposable in-memory SQLite
- 85 frontend tests passed
- frontend build and lint passed
- shell auth guard and dev worktree preservation passed
- static ops contract and Compose YAML syntax passed
- Environment limit: Docker Compose unavailable; Linux-only deployment regression encountered macOS stat -c incompatibility

CI repair after 43119607127: replace the child-shell environment assertion with an explicit environment check accepted by ShellCheck. Existing locked production dependencies failed the unchanged security gates. Update only Axios 1.21.1, follow-redirects 1.16.3, certifi 2026.10.23, Django REST framework 3.18.3 and urllib3 2.8.0. DRF's requirement admits the patched 3.18 series; Django remains on 5.2. Hash-locked Python requirements were regenerated with the existing pip-compile workflow.

After these changes: all 388 backend tests pass against disposable in-memory SQLite, 85 frontend tests and the frontend build pass, ShellCheck passes all scripts, npm production audit reports 0 vulnerabilities, and pip-audit reports no known vulnerabilities. See [DRF release notes](https://www.django-rest-framework.org/community/release-notes/#318x-series) and the [Axios advisory](https://github.com/advisories/GHSA-vh66-26gq-q6x8). PostgreSQL and image checks are delegated to the new dev CI run.
