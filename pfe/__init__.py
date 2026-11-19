"""Project Flow Explainer core package.

The package holds every static-analysis responsibility so the two front ends
(`scripts/build_flow.py` CLI and the DSH adapter) share one implementation and
one evidence model:

  policy    path rules, artifact containment, slugs, atomic writes
  text      diacritic folding and timestamps
  facts     repository scan -> static facts (files, symbols, routes, imports,
            call sites, error sites, budgets)
  flow      flow projection selected from the facts by a flow request
  ontology  entity/relation/confidence vocabulary and fact validation
  index     local incremental index at <repo>/.pfe/index (SQLite + FTS5)
  vectors   optional local-only embedding backends (no network, ever)
  retrieval hybrid retrieval: exact -> vector candidates -> graph -> rerank
  impact    impact analysis, artifact/knowledge verification, refresh

Core rule: this package never imports DSH/Node and never calls the network.
"""

__all__ = [
    "policy", "text", "facts", "flow", "ontology", "index", "vectors",
    "retrieval", "impact",
]

FLOW_SCHEMA_VERSION = 2
KNOWLEDGE_SCHEMA_VERSION = 1
INDEX_VERSION = 1
