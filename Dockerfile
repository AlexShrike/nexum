FROM python:3.13-slim

WORKDIR /app

# Install Poetry
RUN pip install poetry

# Copy project files
COPY pyproject.toml poetry.lock ./
RUN poetry install --no-root --no-dev

# Copy source
COPY core_banking/ core_banking/
COPY dashboard/ dashboard/

# Install the project
RUN poetry install --no-dev

EXPOSE 8090 8890

CMD ["poetry", "run", "uvicorn", "core_banking.api_old:app", "--host", "0.0.0.0", "--port", "8090"]