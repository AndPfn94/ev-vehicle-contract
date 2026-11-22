# Vehicle Data Contract

Release candidate **1.0.0-rc.2**, contract **1.0**.
Publisher **AndPfn94**. SPDX-License-Identifier **Apache-2.0**.

This independent contract defines how read-only vehicle data is supplied.
A Provider obtains source data. A Vehicle Data Service maintains a normalized
cache. A Client reads that cache on behalf of a Consumer. These roles can be
implemented in any language by any application or manufacturer.

The package includes schemas, examples, Provider metadata, configuration,
a validator and independent tests. Licensing and provenance are documented in
[LICENSE](LICENSE), [NOTICE](NOTICE), [LICENSING.md](LICENSING.md) and
[PROVENANCE.md](PROVENANCE.md).
MUST, MUST NOT and SHOULD indicate normative requirements.

## Scope and control authority

Providers and Vehicle Data Services supply telemetry only. This contract
grants no charger, stationary-battery, vehicle-limit, charging-program,
site-limit, Consumer-administration or update authority. The Consumer owns
its charging decisions, local safety limits and any target-SoC stop.

Missing or old data, cloud failures and service outages MUST leave normal
local charging governed by the Consumer's local mode and protection rules.
Stale values, estimates and unqualified data cannot authorize a precise
target-SoC stop.

## Schemas

The schemas use JSON Schema Draft 2020-12 with format checking enabled.
Apply the semantic requirements below in addition to schema validation.

| File | Resource identifier |
| --- | --- |
| vehicle-data.schema.json | https://github.com/AndPfn94/ev-vehicle-contract/schemas/1.0/vehicle-data.schema.json |
| provider.schema.json | https://github.com/AndPfn94/ev-vehicle-contract/schemas/1.0/provider.schema.json |

These versioned HTTPS identifiers name schema resources. Validators resolve
them through a local registry containing the supplied files. Validation
operates offline. Arbitrary external schema retrieval is excluded.

The telemetry schema defines sample, estimate, entry, request and response.
The metadata schema defines provider and config. The schema roots also
validate the corresponding complete documents.

## Actual measurements and units

A sample requires version=1, vehicle, measured_at and quality.
Its remaining fields are optional and may be null.

| Field | Meaning |
| --- | --- |
| vehicle | Stable local alias, 1–64 ASCII characters, starting alphanumerically, followed by alphanumeric characters, underscore, dot, colon or hyphen |
| measured_at | Actual measurement time in UTC with Z, up to six fractional second digits |
| quality | valid, stale, unavailable or simulated |
| soc | Finite fraction 0–1 of the vehicle-reported state of charge |
| charge_limit | Effective read-only vehicle-side AC charging limit, fraction 0–1 |
| plugged_in, moving | Observed booleans or null |
| charging_state | idle, charging, complete, error or null |
| range_km | 0–10,000 km or null |

Unknown values MUST remain unknown. They MUST NOT become invented zeroes
or false states. Reject numeric booleans, out-of-range numbers, NaN and
Infinity. Normalize a percentage exactly once by dividing by 100.
A Consumer's desired target is separate from the vehicle's AC charge_limit.

All supplied sample fields share the same actual measurement time and quality.
Omit fields that cannot be attributed to that time. Cache reads, retries,
restarts and retransmissions MUST NOT advance measured_at.

valid requires an actual vehicle measurement with an evidenced source time.
An unknown source time is represented by sample=null and status
source_time_unknown. The core sample schema recognizes simulated, while
snapshot entries MUST reject simulated samples. Consumers qualify sources
locally. A valid label grants no control authority.

## Reception, freshness and failure

received_at is the Vehicle Data Service's original reception time of the
sample. generated_at is the snapshot creation time. A Consumer MUST also
record its own reception time. Cached responses preserve received_at.
When sample=null, received_at=null.

A Client checks measured_at no later than received_at, received_at no later
than generated_at, and estimate.calculated_at no later than generated_at.
A Consumer also checks these timestamps against its local clock and policy.

An ok entry contains an actual sample with quality=valid. A retained actual
sample under another status has quality=stale. A stale entry requires a
retained sample. A failure without retained data has sample=null.
Consumers independently downgrade old ok values and explicitly mark cached
actual readings unqualified after a source failure. Repeated or older
timestamps create no new evidence and cannot restore freshness.

Status values are ok, stale, offline, auth_required, rate_limited,
unknown_vehicle, source_time_unknown and cost_blocked. retry_after_s is null
or an integer from 1 to 86,400 seconds. It is a cooldown, without requesting
a source refresh.

## Unix socket protocol

Use AF_UNIX SOCK_STREAM with a locally provisioned path, for example
/run/vehicle-data/telemetry.sock.

Each connection carries exactly one request and one response. Each is a
compact UTF-8 JSON object followed by LF. The request has contract_version=1.0,
operation=snapshot, request_id and 1–12 unique vehicle aliases.
Its total size including LF is at most 8,192 bytes. The response including
LF is at most 131,072 bytes. Each embedded sample is at most 8,192 bytes.
Encode Unicode directly as UTF-8.

The response echoes request_id and contains exactly the requested aliases,
each once, in any order. Unknown aliases receive unknown_vehicle with
sample=null. The service closes after its response. An invalid request or
unsupported version causes closure without a data response. The Client
reports a local protocol error.

Reject duplicate keys, invalid UTF-8, non-JSON numbers, additional frames,
truncation and oversize. A Client uses an overall response deadline of four
seconds, permits at most one outstanding request and waits at least
30 seconds after a transport failure before retrying. File validation
does not replace bounded wire parsing.

snapshot MUST read only cached data. It MUST NOT trigger a source query,
vehicle wake-up or token refresh. Provider work runs outside Consumer control
cycles and user-interface requests. Restart, socket failure and the failure
of one vehicle MUST NOT block other vehicles or normal local charging.

## Estimates, identity and sessions

estimate contains soc, calculated_at and method. Allowed methods are
source_estimate, energy_integration and manual. It may accompany the last
actual sample. calculated_at is computation time and cannot qualify an
actual vehicle measurement. External estimates are display information only.

A Consumer MUST keep estimated and actual SoC separate. It MUST NOT put an
estimate into sample.soc with quality=valid. A local charging-energy estimate
requires an actual measurement anchor, usable battery capacity, efficiency
and qualified charger energy attributable to the same transaction.

Explicit local mapping binds a provisioned service identity, source
configuration and vehicle alias to exactly one Consumer profile. Alias
changes require deliberate remapping. Vehicles have independent caches,
with at most twelve configured profiles.

The Consumer explicitly selects the active vehicle and charging session.
Charger, connection and transaction changes discard the association.
Vehicle alias, plugged_in and SoC alone do not prove session association.

A precise target-SoC stop needs a qualified actual measurement after that
association, at most five minutes old, with no future timestamp, matching
source and a still-valid charging session. Old data, estimates and source
failures cannot authorize the stop. Local charging continues according to
the local mode, site power management and device protection.

## Provider metadata and configuration

provider.schema.json defines Provider metadata and configuration version 1.0.
Metadata is versioned data supplied by an implementation. source_kind is
manufacturer for a direct manufacturer source or integration for a general
intermediary or adapter. These categories prescribe no particular software
and grant no permissions.

Metadata fields support text, integer, number, boolean, select and secret_ref.
Keys are unique. select requires choices. Required fields, types, numeric
bounds and unknown keys are checked locally. Persist Provider ID and exact
Provider version.

Metadata is untrusted data. A user explicitly selects a source. Metadata
MUST NOT install code or automatically qualify actual measurements.
Documentation links are displayed as text and opened only on user action.
Their content is never loaded as form code.

Validate schema and semantics before generating YAML 1.2 Core. JSON is the
canonical data model. examples/config.json and examples/config.yaml describe
the same configuration. Quote strings and preserve boolean and numeric types.
Reject custom tags, templates, executable code, command lines, arbitrary
schema retrieval, duplicate keys, aliases, anchors and multiple YAML documents.

Validate changes against the selected Provider version and write atomically.
Failure preserves the last valid configuration. Changing Provider requires
renewed association. secret_ref is an alias in the service's private
credential store. A form directs the user to that service's own authorization
or setup. Passwords, API keys and refresh tokens MUST NOT enter Consumer
configuration or metadata. Secret fields have no default.

## Cost and query controls

poll_interval_s is at least the Provider's minimum interval. Use cache-first
access, account-wide single flight, authorization checks and bounded backoff.
Respect quotas, vehicle sleep and Retry-After. User-interface reads never
initiate source queries or implicit wake-ups.

Version 1.0 fixes allow_paid_requests=false. With cost_class paid or unknown,
only existing free cache or push data is usable. Block queries whose price
is unknown. Paid queries require a separately specified extension, explicit
account-owner consent and a durable monthly budget safe across concurrency
and restarts. Provider metadata cannot grant that consent.

## Security and deployment

The service has its own unprivileged Unix identity. Its /run directory is
managed by that identity or root, mode 0750. The socket is mode 0660 with
a dedicated Client reader group. Connecting requires socket write permission.
The sole snapshot operation enforces the read-only protocol boundary.

Validate the provisioned path, owner, group and Linux SO_PEERCRED locally.
A JSON UID MUST NOT be trusted. Reject unexpected symlinks and parent paths
writable by another identity. Credential directories are mode 0700 and
credential files mode 0600.

Services MUST NOT issue control commands, vehicle wake-ups, charge-limit
writes or target writes. Any separately provisioned telemetry key is scoped
to one profile. Clients receive only normalized telemetry. Exclude VINs,
locations, trips, account identities, raw source responses and error text
containing credentials.

Source access uses user authorization and permitted read endpoints.
Credentials stay with the service. A Consumer that controls a charger
establishes a single deliberate control authority for it.

Bounded messages, cached reads and one background worker support small
deployments. CPU, memory and restart limits need implementation-specific
configuration and measurement on the target system.

## Versioning and verification

VERSION identifies package 1.0.0-rc.2. contract_version and schema_version
remain 1.0. Mandatory telemetry fields, units, quality semantics, version
recognition and control authority require a new major version when changed.
Additional wire fields require explicit negotiation, since version 1.0 rejects
unknown fields. Editorial corrections use package patch revisions.
A final v1.0.0 tag requires separate technical and domain approval.

Install test requirements and run from the package root.

```sh
python -m pip install -r requirements-test.txt
python -m unittest discover -s tests -v
python conformance.py --request examples/request.json --response examples/real.json
```

Independent tests cover schemas, configuration, examples, semantics and
actual local Unix socket exchanges with separate service and Client fixtures.
Synthetic fixtures do not qualify production identity enforcement, source
authenticity, hardware behavior, service isolation or resource limits.

See [CHANGELOG.md](CHANGELOG.md) and
[JSON Schema Draft 2020-12](https://json-schema.org/draft/2020-12/schema).
