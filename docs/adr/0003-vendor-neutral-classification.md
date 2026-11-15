# 0003. Text classification behind a provider-neutral interface

* Status: Accepted
* Date: 2026-11-14

## Context

Sentiment, materiality and event-type scores come from a hosted classifier. Providers and
models change quickly; the first one may not be the one used a year from now.

## Decision

Classification is an interface in `eventalpha.classification` with one module per provider
under `providers/`. The provider and model are configuration (`CLASSIFIER_PROVIDER`,
`CLASSIFIER_MODEL`). Scores are stored with an internal `<provider>:<model>` identifier that
never appears in the API or the UI.

## Consequences

* Switching providers is a new provider module and a config change; DAGs, schema, API and UI
  stay as they are.
* Stored scores remain traceable to the model that produced them, so a model change can be
  compared or rescored.
* The common interface is limited to what every provider can answer (probabilities per
  question), so provider-specific extras need an explicit extension.
