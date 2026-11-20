# API

Later phase: Python 3.12 FastAPI, Entra bearer-token validation, `/healthz`,
managed-identity Azure clients, and an API Dockerfile. The infrastructure placeholder
is not this API. Production containers must listen on port 8000 and serve `/healthz`.
Never log customer content unless `LOG_CONTENT=true` in dev.
