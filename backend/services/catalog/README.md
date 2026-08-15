# Conservative TourAPI catalog enrichment

This service enriches only an existing `WaterSpot` carrying an explicit,
curated `tourapi_id`. It calls the typed TourAPI `detailCommon2` client and has
no search, nearby-discovery, classification, or `WaterSpot` creation path.

Provider title, address, latitude, longitude, HTTPS image, and plain-text
overview map to `name`, `address`, `lat`, `lng`, `image_url`, and `description`.
By default, a usable provider value fills only an empty local field. For the
legacy non-null coordinate columns, numeric zero is treated as the un-geocoded
placeholder. Existing non-empty values change only when the caller explicitly
sets `overwrite=True`.

All detail responses and content IDs are validated before any database write.
The persistence phase locks the selected rows and runs in one transaction,
revalidating each curated ID. Repeating a run with the same input produces no
additional changes. Dry-run returns the same field-level plan without writing.

The report contains only typed provenance: provider name, public source page,
query-free endpoint path, curated content ID, language, and provider-modified
time. The database persistence transaction stores the applicable WaterSpot
fields as `catalog_source=TourAPI`, the public Data.go.kr page in
`catalog_source_url`, the upstream `modifiedtime` in `catalog_verified_at`, and
`catalog_verification=verified`. When TourAPI omits `modifiedtime`, the source is
still recorded but verification remains `partial` with a null verified time.
Using the upstream timestamp rather than the local command clock makes a replay
of identical evidence idempotent. Content fields and these provenance fields are
written in the same locked transaction.

The service never includes raw payloads, request parameters, prepared URLs, or
credentials. HTML descriptions are reduced to normalized visible text, blocked
element bodies such as scripts are discarded, and only absolute credential-free
HTTPS image URLs are accepted.

## Curated identifier migration preflight

`tourapi_id` and `khoa_beach_code` are unique when nonblank. Before applying
`spots.0003_unique_curated_provider_identifiers` to an existing database, deploy
the compatible command code and run:

```bash
python manage.py sync_tour_spots --audit-identifiers
```

This audit reads neither provider credentials nor remote APIs and never changes
rows. If it reports duplicate groups, review and resolve those curated mappings
manually before migration. Neither the audit nor the migration chooses a winner,
deletes a row, or rewrites an official identifier. The migration intentionally
fails with a clear error while any duplicate nonblank identifier remains.
