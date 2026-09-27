"""Business orchestration: use-case logic that is neither HTTP semantics nor a framework port.

Adapters (`src.adapters`) implement `ouroboros.ports` protocols; routes (`src.api`)
own HTTP. What is left — assembling a framework run from persisted state and writing the
outcome back — lives here, so the routes stay thin.
"""
