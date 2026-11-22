# Provider cost policy

SPDX-License-Identifier: Apache-2.0.

This profile defines the minimum behavior for a Provider or Vehicle Data
Service that enables potentially billable telemetry acquisition under
configuration 1.1. Each implementation defines its private policy format,
storage, account setup, price sources and audit interface. The public
configuration carries an opt-in flag and an opaque policy reference.
Implementations MUST enforce the following requirements in the acquisition
path before dispatching potentially billable operations.

## Authorization and price

- Resolve the reference in the service's trusted local policy state. Check
  a durable record of the API account holder's explicit authorization for
  the applicable Provider, billing account and usage scope. Scope the
  record to the relevant sources, operations and vehicles as applicable.
  Check for expiration, withdrawal and scope changes before each attempt.
  Changes to account, Provider or authorized usage require an explicit
  authorization covering the new scope.
- Know the applicable Provider, cost unit and price basis before sending an
  operation. Keep the source or revision of the price, its applicability
  and a bounded validity period. Estimate the entire operation in the
  budget's unit. A temporary credit, trial or allowance can affect the
  estimate only while its terms and remaining applicable balance can be
  verified. Block if the price, its current validity or an upper estimate
  cannot be established. Apply these checks to potentially billable setup,
  credential refresh, retries and probes as well as telemetry reads.

## Budget and dispatch

- Persist an auditable estimated-cost budget with an explicit limit, cost
  unit, billing scope and accounting period. Count committed estimates and
  outstanding reservations. Coordinate all workers, vehicles and sources
  drawing on the same budget. Enforce any narrower applicable limit too.
  Block new potentially billable operations if budget state is unavailable,
  inconsistent or exhausted.
- Atomically check available budget and durably reserve the estimated cost
  before dispatch. Use account-wide single flight and deduplication for
  equivalent work. Restore reservations, cooldowns and retry state after
  restart. Keep estimates for ambiguous outcomes accounted for until they
  can be reconciled, including across accounting-period changes. Never release
  a reservation solely because of a timeout or restart. Any
  subsequent potentially billable attempt needs its own budget check and
  reservation.
- Keep a bounded audit record of the authorization scope, price basis,
  estimated amount, reservation and outcome. Keep account identifiers,
  credentials, tariff data and budget records in the service domain.
  Report failures through existing telemetry statuses and local
  diagnostics. A software estimate cannot guarantee a third party's
  invoice or future free allowances.

Conformance of the public configuration establishes the shape of the
opt-in. Each implementation qualifies account binding, concurrent budget
admission, restarts with outstanding reservations, ambiguous outcomes,
retries, revocation, stale quotes and exhaustion with its own tests before
permitting live paid acquisition.
