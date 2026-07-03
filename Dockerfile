FROM python:3.11-slim
WORKDIR /app
# git: lets app/version.py read the running commit id/dirty-state from the
# repo mounted read-only at /repo, for correlating logs with the exact
# code that produced them (plan/06-performance-investigation.md).
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml ./
COPY app ./app
RUN pip install --no-cache-dir -e ".[dev]"
# NER model for glossary proper-noun filtering
# (plan/07-troubleshooting-backlog.md#b-1). heuristic.py degrades to
# skipping that filter if this is ever missing, so a failed/skipped
# download here doesn't break the rest of the app.
RUN python -m spacy download en_core_web_sm
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
