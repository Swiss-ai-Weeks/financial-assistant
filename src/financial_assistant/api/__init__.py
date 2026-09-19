"""
HTTP layer for the portfolio news desk.

    controllers   HTTP in / HTTP out, no business rules
    services      use cases, orchestration, business rules
    repositories  everything that touches disk or the network

Domain logic (detectors, retrieval, LLM stages, ClaimGraph)
stays in the sibling packages and knows nothing about HTTP.
"""
