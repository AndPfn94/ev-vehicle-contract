# Changelog

## 1.1.0-rc.1

- Add optional Provider configuration 1.1 with an explicit paid opt-in
  and a reference to an implementation-owned cost policy. Omission is safe.
- Require account-holder authorization, current pricing and durable budget
  enforcement before the Provider dispatches a potentially billable call.
- Add an offline version-aware configuration check and synthetic paid
  configuration examples. Existing 1.0 documents remain valid with their
  original schema and paid-request prohibition.
- Preserve Provider metadata 1.0, telemetry schema 1.0 and the read-only
  cache snapshot protocol byte-for-byte at their schema resources.

## 1.0.0-rc.2

- Specify general Consumer, Vehicle Data Service, Client and Provider roles.
- Use neutral versioned schema identifiers.
- Use manufacturer and integration as Provider source categories.
- Preserve telemetry fields, units, quality, times, framing and cost controls.
- Clarify publisher attribution and AI-assisted provenance.
- Add schema, configuration and actual Unix socket conformance tests.

Importing earlier Provider metadata requires explicit mapping of any earlier
application-specific source categories to integration. The category
manufacturer is retained. Older closed-enumeration validators require an
update before accepting integration. Telemetry wire documents are unaffected.

Schema registries using an earlier identifier need an updated local mapping
or reference. Consumers should pin the reviewed candidate commit.
Final version 1.0.0 requires separate domain and technical approval.
