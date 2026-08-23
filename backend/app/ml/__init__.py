"""Machine-learning pipeline: preprocessing, model providers, explainability.

Layout note: runtime ML code lives here so the API service and the background
worker can both import it. The top-level ``ml/`` directory holds training,
evaluation and model artefacts, which are never imported by the backend.
"""
