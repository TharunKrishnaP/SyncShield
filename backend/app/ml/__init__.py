"""Trained ML layer for the FDR backend (Phase 1).

Modules here wrap trained artifacts produced by the ``ml/`` workspace
(repo root) and expose fail-soft interfaces: if a model artifact is missing,
``available`` is False and callers fall back to the existing rule engines.
"""