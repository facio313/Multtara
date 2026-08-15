# PongDang deterministic recommendation engine

This package is a pure-Python decision layer. It has no database, HTTP, Django,
LLM, or OR-Tools dependency. Callers normalize provider evidence into immutable
domain objects and inject a travel-time provider.

## Decision order

1. **Mandatory hard gates** — safety and operation must explicitly be
   `ALLOW`; unknown fails closed. Accessibility and pet policy must explicitly
   allow the request when the party needs them. Age rules must be known and
   every party member must be inside the permitted range. These facts never
   become compensating score weights.
2. **Continuous preference match** — each observed feature uses
   `1 - abs(user_target - candidate_value)`. Weighted matches are averaged on
   the available feature evidence. A persona label is retained for display or
   analytics only and is not read by the scorer.
3. **Uncertainty penalty** — preference evidence confidence is multiplied by
   weighted feature coverage. The default final score is
   `base * (1 - 0.35 * (1 - confidence * coverage))`. Missing all requested
   features makes the candidate ineligible; uncertainty never turns a failed
   safety gate into an eligible item.
4. **Diversity** — deterministic maximal marginal relevance (MMR) balances the
   score against Jaccard overlap of explicit activity, region, and content tags.
   The configurable default relevance floor is 50/100, so novelty cannot insert
   a nearly irrelevant candidate merely to make the list look varied. Stable
   spot IDs break exact ties.
5. **Itinerary feasibility** — the dependency-free greedy baseline considers
   reward per incremental minute, with deterministic tie breaks. Every accepted
   visit respects its duration and one of its time windows, the cumulative
   budget, known travel times, and a known on-time route to the final location.

In bad-weather mode, the planner excludes every candidate that is not both
`indoor` and `bad_weather_suitable`. This is a verified fallback filter, not a
weather safety inference, and it cannot override a safety or operation gate.

## Integration boundary

Activity-specific official indices or curated suitability values (for example,
surfing or mudflat suitability) may be supplied as continuous features. The
upstream integration must separately turn current authoritative closure,
warning, operation, accessibility, pet, and age evidence into the structured
hard-gate fields. Free text and model-generated judgments are not accepted as a
safety decision path.

The request carries an explicit `participant_skill_level`. An adult beginner
swimmer uses the same conservative participant profile as a family swimmer. A
surfing grade is usable only when its authoritative KHOA `GrdCn` text maps to
the requested skill through an evidence-backed exact allowlist; unspecified,
unknown, or mismatched details remove the official grade from request-time
evaluation and therefore fail closed.

`TravelTimeProvider` is the provider interface. `TravelTimeMatrix` is an
immutable precomputed implementation useful for tests, cache snapshots, and
small searches. A production adapter may use a separately refreshed routing
matrix, but it should not perform nondeterministic network calls during a plan.

## Known limitations

- The greedy itinerary is a transparent baseline; it does not prove a globally
  optimal orienteering solution and may miss a better combination of visits.
- MMR quality depends on curated tags. It provides result-set variety, not a
  guarantee of geographic, cultural, or accessibility fairness.
- Confidence and coverage describe preference evidence only. They are not a
  probability of safety and must never replace authoritative hard gates.
- The engine assumes upstream gate status, operating windows, costs, durations,
  and travel times are current and correctly normalized for the requested day.
- Time is represented as same-day minutes after midnight. Overnight windows,
  dates, time zones, capacity, reservations, traffic uncertainty, and group
  splitting are outside this baseline.
- A verified indoor fallback may still be unavailable because of a later
  closure or route warning. Upstream evidence must refresh the hard gates.
- The engine does not invent universal thresholds for surfing, mudflats, hot
  springs, rafting, valleys, or water-view relaxation. Domain methodology and
  local/official rules belong in the upstream evidence layer.
