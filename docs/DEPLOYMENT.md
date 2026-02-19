# Deployment Guide

This guide covers deployment patterns for Nexum core banking system from development through production, including containerization, environment configuration, monitoring, and scaling considerations.

---

## Table of Contents

1. [Development Setup](#development-setup)
2. [Staging Environment](#staging-environment)
3. [Production Deployment](#production-deployment)
4. [Docker Deployment](#docker-deployment)
5. [Environment Variables Reference](#environment-variables-reference)
6. [Health Checks](#health-checks)
7. [Monitoring and Logging](#monitoring-and-logging)
8. [Backup and Recovery](#backup-and-recovery)
9. [Scaling Considerations](#scaling-considerations)
10. [Infrastructure as Code](#infrastructure-as-code)

---

## Development Setup

### Local Development Environment

**Prerequisites:**
- Python 3.12+
- Poetry for dependency management
- PostgreSQL 15+ (or SQLite for simple development)
- Redis (optional, for caching and rate limiting)

**Setup steps:**

```bash
# Clone repository
git clone https://github.com/yourcompany/nexum-core-banking.git
cd nexum-core-banking

# Use shared virtual environment
source /path/to/shared/venv/bin/activate

# Install dependencies
poetry install -E full

# Set up development environment
cp .env.example .env.development

# Configure development database
export NEXUM_DATABASE_URL="postgresql://nexum_dev:password@localhost:5432/nexum_dev"
export NEXUM_LOG_LEVEL="DEBUG"
export NEXUM_JWT_SECRET="dev-secret-change-in-production"
export NEXUM_ENCRYPTION_ENABLED="false"  # Disable encryption for development

# Run database migrations
python -c "
from core_banking.storage import PostgreSQLStorage
from core_banking.migrations import MigrationManager
from core_banking.config import get_config

config = get_config()
storage = PostgreSQLStorage(config.database_url)
mm = MigrationManager(storage)
mm.migrate_up()
"

# Start development server with hot reload
uvicorn core_banking.api:app --reload --host 0.0.0.0 --port 8090
```

**Development environment variables:**

```bash
# .env.development
NEXUM_DATABASE_URL=postgresql://nexum_dev:password@localhost:5432/nexum_dev
NEXUM_LOG_LEVEL=DEBUG
NEXUM_LOG_FORMAT=text
NEXUM_JWT_SECRET=dev-secret-change-in-production
NEXUM_JWT_EXPIRY_HOURS=24
NEXUM_ENCRYPTION_ENABLED=false
NEXUM_ENABLE_RATE_LIMITING=false
NEXUM_CORS_ORIGINS=*
NEXUM_API_WORKERS=1
```

### Development Database Setup

**PostgreSQL for development:**

```bash
# Create development database
createdb nexum_dev
createuser nexum_dev --createdb
psql -d nexum_dev -c "ALTER USER nexum_dev PASSWORD 'password';"
psql -d nexum_dev -c "GRANT ALL PRIVILEGES ON DATABASE nexum_dev TO nexum_dev;"

# For PostgreSQL 15+, grant schema privileges
psql -d nexum_dev -c "GRANT ALL ON SCHEMA public TO nexum_dev;"
```

**SQLite for simple development:**

```bash
# Use SQLite for simple local development
export NEXUM_DATABASE_URL="sqlite:///nexum_dev.db"
```

### Development Tools

**Testing setup:**

```bash
# Run all tests
python -m pytest tests/ -v

# Run with coverage
python -m pytest tests/ --cov=core_banking --cov-report=html

# Run specific test categories
python -m pytest tests/test_transactions.py -v
python -m pytest tests/test_loans.py -v
python -m pytest tests/test_security.py -v
```

**API documentation:**

```bash
# Start server and view API docs
python run.py

# Visit interactive documentation
open http://localhost:8090/docs
open http://localhost:8090/redoc
```

---

## Staging Environment

### Staging Infrastructure

Staging should mirror production as closely as possible:

**Infrastructure components:**
- Application server (2 instances for load balancing)
- PostgreSQL database (single instance with automated backups)
- Redis cache (single instance)
- Load balancer (nginx or cloud provider)
- Log aggregation (ELK stack or cloud logging)

### Staging Configuration

**Environment variables for staging:**

```bash
# .env.staging
NEXUM_DATABASE_URL=postgresql://nexum_staging:secure_pass@db-staging:5432/nexum_staging
NEXUM_LOG_LEVEL=INFO
NEXUM_LOG_FORMAT=json
NEXUM_JWT_SECRET=staging-jwt-secret-256-bits
NEXUM_JWT_EXPIRY_HOURS=8
NEXUM_ENCRYPTION_ENABLED=true
NEXUM_ENCRYPTION_MASTER_KEY=staging-encryption-key-base64
NEXUM_ENCRYPTION_PROVIDER=aesgcm
NEXUM_ENABLE_RATE_LIMITING=true
NEXUM_CORS_ORIGINS=https://staging-app.yourbank.com
NEXUM_API_WORKERS=2
NEXUM_ENABLE_KAFKA_EVENTS=true
NEXUM_KAFKA_BOOTSTRAP_SERVERS=kafka-staging:9092
```

### Staging Deployment with Docker Compose

```yaml
# docker-compose.staging.yml
version: '3.8'

services:
  nexum-api:
    build:
      context: .
      target: production
    image: nexum-core-banking:staging
    ports:
      - "8090:8090"
    environment:
      - NEXUM_DATABASE_URL=postgresql://nexum_staging:${DB_PASSWORD}@postgres:5432/nexum_staging
      - NEXUM_JWT_SECRET=${JWT_SECRET}
      - NEXUM_ENCRYPTION_MASTER_KEY=${ENCRYPTION_KEY}
      - NEXUM_LOG_LEVEL=INFO
      - NEXUM_API_WORKERS=2
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8090/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s
    restart: unless-stopped
    volumes:
      - ./logs:/app/logs

  postgres:
    image: postgres:15
    environment:
      - POSTGRES_DB=nexum_staging
      - POSTGRES_USER=nexum_staging
      - POSTGRES_PASSWORD=${DB_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./sql/init-staging.sql:/docker-entrypoint-initdb.d/init.sql
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U nexum_staging"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped

  redis:
    image: redis:7-alpine
    command: redis-server --requirepass ${REDIS_PASSWORD}
    healthcheck:
      test: ["CMD", "redis-cli", "--raw", "incr", "ping"]
      interval: 10s
      timeout: 3s
      retries: 5
    restart: unless-stopped

  nginx:
    image: nginx:alpine
    ports:
      - "443:443"
      - "80:80"
    volumes:
      - ./nginx/staging.conf:/etc/nginx/conf.d/default.conf
      - ./ssl:/etc/ssl/certs
    depends_on:
      - nexum-api
    restart: unless-stopped

volumes:
  postgres_data:
```

### Staging Deployment Commands

```bash
# Build and deploy to staging
docker-compose -f docker-compose.staging.yml build
docker-compose -f docker-compose.staging.yml up -d

# View logs
docker-compose -f docker-compose.staging.yml logs -f nexum-api

# Run health checks
curl -f https://staging-api.yourbank.com/health

# Run integration tests against staging
python -m pytest tests/integration/ --base-url=https://staging-api.yourbank.com
```

---

## Production Deployment

### Production Architecture

**Recommended production architecture:**

```
                     ┌─────────────┐
                     │ Load        │
    Internet ────────┤ Balancer    │
                     │ (nginx/ALB) │
                     └──────┬──────┘
                            │
                 ┌──────────┴──────────┐
                 │                     │
         ┌───────▼───────┐    ┌───────▼───────┐
         │ Nexum API     │    │ Nexum API     │
         │ Instance 1    │    │ Instance 2    │
         │ (Docker)      │    │ (Docker)      │
         └───────┬───────┘    └───────┬───────┘
                 │                     │
                 └──────────┬──────────┘
                            │
                 ┌──────────▼──────────┐
                 │ PostgreSQL Cluster  │
                 │ (Primary + Replica) │
                 └─────────────────────┘
                            │
                 ┌──────────▼──────────┐
                 │ Redis Cluster       │
                 │ (Cache + Sessions)  │
                 └─────────────────────┘
```

### Production Environment Variables

**Secure environment configuration:**

```bash
# /etc/nexum/production.env
NEXUM_DATABASE_URL=postgresql://nexum_prod:${DB_PASSWORD}@prod-db-cluster:5432/nexum_production
NEXUM_DATABASE_POOL_SIZE=20
NEXUM_DATABASE_POOL_OVERFLOW=30
NEXUM_DATABASE_POOL_TIMEOUT=30

# Security
NEXUM_JWT_SECRET=${JWT_SECRET_FROM_VAULT}
NEXUM_JWT_EXPIRY_HOURS=4
NEXUM_ENCRYPTION_ENABLED=true
NEXUM_ENCRYPTION_MASTER_KEY=${ENCRYPTION_KEY_FROM_VAULT}
NEXUM_ENCRYPTION_PROVIDER=aesgcm

# API Configuration
NEXUM_API_HOST=0.0.0.0
NEXUM_API_PORT=8090
NEXUM_API_WORKERS=4
NEXUM_API_TIMEOUT=60
NEXUM_API_MAX_REQUEST_SIZE=16777216

# Security & Rate Limiting
NEXUM_ENABLE_RATE_LIMITING=true
NEXUM_RATE_LIMIT_GLOBAL=2000
NEXUM_RATE_LIMIT_AUTH=20
NEXUM_CORS_ORIGINS=https://app.yourbank.com,https://admin.yourbank.com

# Logging
NEXUM_LOG_LEVEL=INFO
NEXUM_LOG_FORMAT=json
NEXUM_LOG_FILE=/var/log/nexum/application.log

# Business Rules
NEXUM_MAX_DAILY_TRANSACTION_LIMIT=100000.00
NEXUM_MAX_TRANSACTION_AMOUNT=500000.00
NEXUM_MIN_ACCOUNT_BALANCE=0.00

# External Services
NEXUM_ENABLE_KAFKA_EVENTS=true
NEXUM_KAFKA_BOOTSTRAP_SERVERS=kafka-prod-cluster:9092
NEXUM_KAFKA_TOPIC_PREFIX=nexum-prod

# Monitoring
NEXUM_ENABLE_METRICS=true
NEXUM_ENABLE_TRACING=false
```

### Systemd Service Configuration

**Create systemd service for production:**

```ini
# /etc/systemd/system/nexum-api.service
[Unit]
Description=Nexum Core Banking API
After=network.target postgresql.service redis.service
Wants=postgresql.service redis.service

[Service]
Type=exec
User=nexum
Group=nexum
WorkingDirectory=/opt/nexum
Environment=PATH=/opt/nexum/.venv/bin
EnvironmentFile=/etc/nexum/production.env
ExecStart=/opt/nexum/.venv/bin/python run.py
ExecReload=/bin/kill -HUP $MAINPID
Restart=always
RestartSec=10
StartLimitIntervalSec=300
StartLimitBurst=5

# Security settings
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ReadWritePaths=/opt/nexum/logs /var/log/nexum
ProtectHome=yes

# Resource limits
LimitNOFILE=65536
MemoryMax=2G
CPUQuota=200%

[Install]
WantedBy=multi-user.target
```

**Enable and start service:**

```bash
# Install and start service
sudo systemctl enable nexum-api.service
sudo systemctl start nexum-api.service

# Monitor service
sudo systemctl status nexum-api.service
sudo journalctl -u nexum-api.service -f

# Restart service
sudo systemctl restart nexum-api.service
```

### Production Database Setup

**PostgreSQL production configuration:**

```bash
# Create production database and user
sudo -u postgres createdb nexum_production
sudo -u postgres createuser nexum_prod --no-createdb --no-createrole --no-superuser
sudo -u postgres psql -c "ALTER USER nexum_prod PASSWORD '$(openssl rand -base64 32)';"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE nexum_production TO nexum_prod;"
sudo -u postgres psql -d nexum_production -c "GRANT ALL ON SCHEMA public TO nexum_prod;"

# Configure PostgreSQL for production
# Edit /etc/postgresql/15/main/postgresql.conf
shared_buffers = 512MB                  # 25% of RAM
effective_cache_size = 1GB             # 50-75% of RAM
maintenance_work_mem = 128MB
checkpoint_completion_target = 0.7
wal_buffers = 16MB
default_statistics_target = 100
random_page_cost = 1.1                 # For SSD storage

# Configure connection limits
max_connections = 200
shared_preload_libraries = 'pg_stat_statements'

# Enable statement logging for monitoring
log_statement = 'mod'                  # Log data-modifying statements
log_min_duration_statement = 1000      # Log slow queries (>1s)
```

**Run production migrations:**

```bash
# Run as deployment user
cd /opt/nexum
source .venv/bin/activate
python -c "
from core_banking.storage import PostgreSQLStorage
from core_banking.migrations import MigrationManager
from core_banking.config import get_config

config = get_config()
storage = PostgreSQLStorage(config.database_url)
mm = MigrationManager(storage)
applied = mm.migrate_up()
for migration in applied:
    print(f'Applied: {migration}')
"
```

---

## Docker Deployment

### Production Dockerfile

```dockerfile
# Multi-stage build for production
FROM python:3.12-slim as builder

# Install build dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN pip install poetry

# Set up application directory
WORKDIR /app

# Copy dependency files
COPY pyproject.toml poetry.lock ./

# Configure Poetry and install dependencies
RUN poetry config virtualenvs.create false \
    && poetry install --only=main -E full --no-dev

# Production image
FROM python:3.12-slim as production

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Create non-root user
RUN groupadd --gid 1000 nexum \
    && useradd --uid 1000 --gid nexum --shell /bin/bash --create-home nexum

# Set up application directory
WORKDIR /app

# Copy Python dependencies from builder stage
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY --chown=nexum:nexum . .

# Create directories for logs and data
RUN mkdir -p /app/logs /app/data \
    && chown -R nexum:nexum /app

# Switch to non-root user
USER nexum

# Expose port
EXPOSE 8090

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8090/health || exit 1

# Default command
CMD ["python", "run.py"]
```

### Docker Compose for Production

```yaml
# docker-compose.production.yml
version: '3.8'

services:
  nexum-api:
    build:
      context: .
      target: production
    image: nexum-core-banking:latest
    deploy:
      replicas: 2
      resources:
        limits:
          cpus: '1.0'
          memory: 2G
        reservations:
          cpus: '0.5'
          memory: 1G
    environment:
      - NEXUM_DATABASE_URL=postgresql://nexum_prod:${DB_PASSWORD}@postgres:5432/nexum_production
      - NEXUM_JWT_SECRET=${JWT_SECRET}
      - NEXUM_ENCRYPTION_MASTER_KEY=${ENCRYPTION_KEY}
      - NEXUM_REDIS_URL=redis://:${REDIS_PASSWORD}@redis:6379/0
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8090/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s
    restart: unless-stopped
    volumes:
      - ./logs:/app/logs
      - ./data:/app/data
    networks:
      - nexum-network

  postgres:
    image: postgres:15
    environment:
      - POSTGRES_DB=nexum_production
      - POSTGRES_USER=nexum_prod
      - POSTGRES_PASSWORD=${DB_PASSWORD}
      - POSTGRES_INITDB_ARGS=--auth-host=scram-sha-256
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./postgresql.conf:/etc/postgresql/postgresql.conf
      - ./init-prod.sql:/docker-entrypoint-initdb.d/init.sql
    command: postgres -c config_file=/etc/postgresql/postgresql.conf
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U nexum_prod"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped
    networks:
      - nexum-network

  postgres-backup:
    image: postgres:15
    environment:
      - PGHOST=postgres
      - PGDATABASE=nexum_production
      - PGUSER=nexum_prod
      - PGPASSWORD=${DB_PASSWORD}
    volumes:
      - ./backups:/backups
      - ./backup-scripts:/scripts
    command: |
      sh -c '
      while true; do
        pg_dump --verbose --clean --no-owner --no-privileges --format=custom > /backups/nexum_backup_$(date +%Y%m%d_%H%M%S).dump
        find /backups -name "*.dump" -mtime +7 -delete
        sleep 86400
      done'
    depends_on:
      postgres:
        condition: service_healthy
    restart: unless-stopped
    networks:
      - nexum-network

  redis:
    image: redis:7-alpine
    command: redis-server --requirepass ${REDIS_PASSWORD} --appendonly yes
    environment:
      - REDIS_PASSWORD=${REDIS_PASSWORD}
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "--raw", "incr", "ping"]
      interval: 10s
      timeout: 3s
      retries: 5
    restart: unless-stopped
    networks:
      - nexum-network

  nginx:
    image: nginx:alpine
    ports:
      - "443:443"
      - "80:80"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf
      - ./nginx/ssl:/etc/nginx/ssl
    depends_on:
      - nexum-api
    restart: unless-stopped
    networks:
      - nexum-network

  kafka:
    image: confluentinc/cp-kafka:7.4.0
    environment:
      KAFKA_BROKER_ID: 1
      KAFKA_ZOOKEEPER_CONNECT: zookeeper:2181
      KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://kafka:9092
      KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR: 1
      KAFKA_TRANSACTION_STATE_LOG_REPLICATION_FACTOR: 1
      KAFKA_TRANSACTION_STATE_LOG_MIN_ISR: 1
      KAFKA_GROUP_INITIAL_REBALANCE_DELAY_MS: 0
    depends_on:
      - zookeeper
    volumes:
      - kafka_data:/var/lib/kafka/data
    restart: unless-stopped
    networks:
      - nexum-network

  zookeeper:
    image: confluentinc/cp-zookeeper:7.4.0
    environment:
      ZOOKEEPER_CLIENT_PORT: 2181
      ZOOKEEPER_TICK_TIME: 2000
    volumes:
      - zookeeper_data:/var/lib/zookeeper/data
    restart: unless-stopped
    networks:
      - nexum-network

networks:
  nexum-network:
    driver: bridge

volumes:
  postgres_data:
  redis_data:
  kafka_data:
  zookeeper_data:
```

### Production Deployment Script

```bash
#!/bin/bash
# deploy-production.sh

set -euo pipefail

echo "Starting Nexum Core Banking production deployment..."

# Load environment variables
if [ -f .env.production ]; then
    export $(grep -v '^#' .env.production | xargs)
fi

# Pre-deployment checks
echo "Running pre-deployment checks..."

# Check required environment variables
required_vars=("DB_PASSWORD" "JWT_SECRET" "ENCRYPTION_KEY")
for var in "${required_vars[@]}"; do
    if [ -z "${!var:-}" ]; then
        echo "Error: $var is not set"
        exit 1
    fi
done

# Build Docker images
echo "Building Docker images..."
docker-compose -f docker-compose.production.yml build

# Run database migrations
echo "Running database migrations..."
docker-compose -f docker-compose.production.yml run --rm nexum-api python -c "
from core_banking.storage import PostgreSQLStorage
from core_banking.migrations import MigrationManager
from core_banking.config import get_config

config = get_config()
storage = PostgreSQLStorage(config.database_url)
mm = MigrationManager(storage)
applied = mm.migrate_up()
print(f'Applied {len(applied)} migrations')
"

# Deploy services
echo "Deploying services..."
docker-compose -f docker-compose.production.yml up -d

# Wait for services to be healthy
echo "Waiting for services to be healthy..."
timeout 300 bash -c 'until curl -f http://localhost:8090/health; do sleep 5; done'

# Run health checks
echo "Running post-deployment health checks..."
python -m pytest tests/health_checks.py --base-url=http://localhost:8090

echo "Production deployment completed successfully!"
```

---

## Environment Variables Reference

### Complete Environment Variables List

| Variable | Default | Description |
|----------|---------|-------------|
| **Database Configuration** | | |
| `NEXUM_DATABASE_URL` | sqlite:///nexum.db | Database connection string |
| `NEXUM_DATABASE_POOL_SIZE` | 5 | Connection pool size |
| `NEXUM_DATABASE_POOL_OVERFLOW` | 10 | Pool overflow limit |
| `NEXUM_DATABASE_POOL_TIMEOUT` | 30 | Connection timeout (seconds) |
| `NEXUM_DATABASE_ECHO` | false | Enable SQL query logging |
| **API Configuration** | | |
| `NEXUM_API_HOST` | 0.0.0.0 | API bind address |
| `NEXUM_API_PORT` | 8090 | API port |
| `NEXUM_API_WORKERS` | 1 | Number of worker processes |
| `NEXUM_API_TIMEOUT` | 60 | Request timeout (seconds) |
| `NEXUM_API_MAX_REQUEST_SIZE` | 16777216 | Max request size (bytes) |
| **Security Configuration** | | |
| `NEXUM_JWT_SECRET` | change-me-in-production | JWT signing secret |
| `NEXUM_JWT_EXPIRY_HOURS` | 24 | JWT token expiry |
| `NEXUM_JWT_ALGORITHM` | HS256 | JWT algorithm |
| `NEXUM_PASSWORD_MIN_LENGTH` | 8 | Minimum password length |
| `NEXUM_SESSION_TIMEOUT_MINUTES` | 30 | Session timeout |
| **Encryption Configuration** | | |
| `NEXUM_ENCRYPTION_ENABLED` | false | Enable PII encryption |
| `NEXUM_ENCRYPTION_MASTER_KEY` | | Base64-encoded master key |
| `NEXUM_ENCRYPTION_PROVIDER` | fernet | Encryption provider |
| **Rate Limiting** | | |
| `NEXUM_ENABLE_RATE_LIMITING` | true | Enable rate limiting |
| `NEXUM_RATE_LIMIT_GLOBAL` | 1000 | Global rate limit (per minute) |
| `NEXUM_RATE_LIMIT_AUTH` | 10 | Auth endpoint limit |
| `NEXUM_RATE_LIMIT_TRANSACTIONS` | 500 | Transaction limit |
| **CORS Configuration** | | |
| `NEXUM_CORS_ORIGINS` | * | Allowed CORS origins |
| **Logging Configuration** | | |
| `NEXUM_LOG_LEVEL` | INFO | Log level |
| `NEXUM_LOG_FORMAT` | json | Log format (json/text) |
| `NEXUM_LOG_FILE` | | Log file path |
| **Business Rules** | | |
| `NEXUM_MIN_ACCOUNT_BALANCE` | 0.00 | Default minimum balance |
| `NEXUM_MAX_DAILY_TRANSACTION_LIMIT` | 10000.00 | Daily transaction limit |
| `NEXUM_MAX_TRANSACTION_AMOUNT` | 100000.00 | Maximum single transaction |
| `NEXUM_INTEREST_CALCULATION_PRECISION` | 4 | Interest decimal precision |
| **Feature Flags** | | |
| `NEXUM_ENABLE_AUDIT_LOGGING` | true | Enable audit trail |
| `NEXUM_ENABLE_KAFKA_EVENTS` | false | Enable Kafka events |
| `NEXUM_ENABLE_METRICS` | true | Enable metrics collection |
| `NEXUM_ENABLE_TRACING` | false | Enable distributed tracing |
| **Kafka Configuration** | | |
| `NEXUM_KAFKA_BOOTSTRAP_SERVERS` | | Kafka bootstrap servers |
| `NEXUM_KAFKA_TOPIC_PREFIX` | nexum | Topic prefix |
| `NEXUM_KAFKA_CONSUMER_GROUP` | nexum-core | Consumer group |
| `NEXUM_KAFKA_BATCH_SIZE` | 100 | Batch size |
| **Performance Configuration** | | |
| `NEXUM_CACHE_TTL_SECONDS` | 300 | Cache TTL |
| `NEXUM_BATCH_PROCESSING_SIZE` | 1000 | Batch processing size |
| `NEXUM_CONNECTION_POOL_SIZE` | 20 | Connection pool size |
| **Migration Configuration** | | |
| `NEXUM_AUTO_MIGRATE` | true | Auto-run migrations |
| `NEXUM_MIGRATION_TIMEOUT_SECONDS` | 300 | Migration timeout |

---

## Health Checks

### Application Health Check

Nexum provides comprehensive health checks for monitoring:

```python
# Health check endpoint returns
{
    "status": "healthy",
    "timestamp": "2024-02-19T15:32:00.000000",
    "version": "1.0.0",
    "components": {
        "database": {
            "status": "healthy",
            "response_time_ms": 2.5,
            "connection_pool": {
                "active": 3,
                "idle": 7,
                "total": 10
            }
        },
        "redis": {
            "status": "healthy", 
            "response_time_ms": 0.8
        },
        "kafka": {
            "status": "healthy",
            "brokers_connected": 3
        },
        "encryption": {
            "status": "enabled",
            "provider": "aesgcm"
        },
        "audit_trail": {
            "status": "healthy",
            "last_entry": "2024-02-19T15:31:45.123456"
        }
    }
}
```

### Docker Health Check

```dockerfile
# Health check in Dockerfile
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8090/health || exit 1
```

### Kubernetes Liveness and Readiness Probes

```yaml
# kubernetes-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: nexum-api
spec:
  replicas: 3
  selector:
    matchLabels:
      app: nexum-api
  template:
    metadata:
      labels:
        app: nexum-api
    spec:
      containers:
      - name: nexum
        image: nexum-core-banking:latest
        ports:
        - containerPort: 8090
        livenessProbe:
          httpGet:
            path: /health
            port: 8090
          initialDelaySeconds: 60
          periodSeconds: 30
          timeoutSeconds: 10
          failureThreshold: 3
        readinessProbe:
          httpGet:
            path: /health/ready
            port: 8090
          initialDelaySeconds: 10
          periodSeconds: 10
          timeoutSeconds: 5
          failureThreshold: 3
        resources:
          requests:
            cpu: 500m
            memory: 1Gi
          limits:
            cpu: 1000m
            memory: 2Gi
```

### External Health Monitoring

**Prometheus metrics endpoint:**

```bash
# Enable metrics collection
export NEXUM_ENABLE_METRICS=true

# Metrics available at /metrics endpoint
curl http://localhost:8090/metrics
```

**Sample metrics:**

```
# HELP nexum_requests_total Total number of requests
# TYPE nexum_requests_total counter
nexum_requests_total{method="POST",endpoint="/transactions"} 1234

# HELP nexum_request_duration_seconds Request duration in seconds
# TYPE nexum_request_duration_seconds histogram
nexum_request_duration_seconds_bucket{method="POST",endpoint="/transactions",le="0.1"} 987

# HELP nexum_database_connections Database connection pool status
# TYPE nexum_database_connections gauge
nexum_database_connections{state="active"} 5
nexum_database_connections{state="idle"} 15

# HELP nexum_transactions_processed_total Total transactions processed
# TYPE nexum_transactions_processed_total counter
nexum_transactions_processed_total{type="deposit",status="completed"} 5678
```

---

## Monitoring and Logging

### Structured Logging

Nexum uses structured JSON logging for production:

```json
{
    "timestamp": "2024-02-19T15:32:00.123456Z",
    "level": "INFO",
    "logger": "core_banking.transactions",
    "message": "Transaction processed successfully",
    "request_id": "req_abc123",
    "user_id": "user_123",
    "transaction_id": "txn_456",
    "account_id": "acc_789",
    "amount": "1500.00",
    "currency": "USD",
    "processing_time_ms": 45.2
}
```

### Log Aggregation with ELK Stack

**Logstash configuration:**

```yaml
# logstash.conf
input {
  file {
    path => "/var/log/nexum/application.log"
    type => "nexum-api"
    codec => "json"
  }
}

filter {
  if [type] == "nexum-api" {
    date {
      match => [ "timestamp", "ISO8601" ]
    }
    
    if [level] in ["ERROR", "CRITICAL"] {
      mutate {
        add_tag => ["alert"]
      }
    }
  }
}

output {
  elasticsearch {
    hosts => ["elasticsearch:9200"]
    index => "nexum-logs-%{+YYYY.MM.dd}"
  }
}
```

### Application Metrics

**Key metrics to monitor:**

| Metric | Type | Description |
|--------|------|-------------|
| `nexum_requests_total` | Counter | Total API requests |
| `nexum_request_duration_seconds` | Histogram | Request processing time |
| `nexum_transactions_processed_total` | Counter | Transactions processed |
| `nexum_database_connections` | Gauge | DB connection pool status |
| `nexum_cache_hits_total` | Counter | Cache hit/miss ratio |
| `nexum_audit_events_total` | Counter | Audit events generated |
| `nexum_errors_total` | Counter | Error count by type |

### Alerting Rules

**Prometheus alerting rules:**

```yaml
# nexum-alerts.yml
groups:
- name: nexum-api
  rules:
  - alert: NexumHighErrorRate
    expr: rate(nexum_errors_total[5m]) > 0.1
    for: 2m
    labels:
      severity: critical
    annotations:
      summary: "High error rate detected"
      description: "Error rate is {{ $value }} errors per second"

  - alert: NexumDatabaseConnectionsLow
    expr: nexum_database_connections{state="idle"} < 2
    for: 1m
    labels:
      severity: warning
    annotations:
      summary: "Low database connections available"

  - alert: NexumRequestLatencyHigh
    expr: histogram_quantile(0.95, rate(nexum_request_duration_seconds_bucket[5m])) > 1
    for: 5m
    labels:
      severity: warning
    annotations:
      summary: "High request latency detected"
```

---

## Backup and Recovery

### Database Backup Strategy

**Automated backup script:**

```bash
#!/bin/bash
# backup-nexum-db.sh

set -euo pipefail

# Configuration
DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5432}"
DB_NAME="${DB_NAME:-nexum_production}"
DB_USER="${DB_USER:-nexum_prod}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/nexum}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"

# Create backup directory
mkdir -p "$BACKUP_DIR"

# Generate backup filename with timestamp
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/nexum_backup_$TIMESTAMP.dump"

# Create database dump
echo "Creating database backup: $BACKUP_FILE"
pg_dump \
    --host="$DB_HOST" \
    --port="$DB_PORT" \
    --username="$DB_USER" \
    --dbname="$DB_NAME" \
    --format=custom \
    --compress=9 \
    --verbose \
    --file="$BACKUP_FILE"

# Verify backup
if pg_restore --list "$BACKUP_FILE" > /dev/null; then
    echo "Backup verification successful"
else
    echo "Backup verification failed!" >&2
    exit 1
fi

# Clean up old backups
find "$BACKUP_DIR" -name "nexum_backup_*.dump" -mtime "+$RETENTION_DAYS" -delete

# Upload to cloud storage (optional)
if command -v aws &> /dev/null; then
    aws s3 cp "$BACKUP_FILE" "s3://your-backup-bucket/nexum/$(basename "$BACKUP_FILE")"
fi

echo "Backup completed successfully: $BACKUP_FILE"
```

### Backup Restoration

**Database restore script:**

```bash
#!/bin/bash
# restore-nexum-db.sh

set -euo pipefail

BACKUP_FILE="$1"
TARGET_DB="${2:-nexum_restored}"

if [ -z "$BACKUP_FILE" ]; then
    echo "Usage: $0 <backup_file> [target_database]"
    exit 1
fi

echo "Restoring from backup: $BACKUP_FILE"
echo "Target database: $TARGET_DB"

# Create target database
createdb "$TARGET_DB"

# Restore database
pg_restore \
    --dbname="$TARGET_DB" \
    --verbose \
    --clean \
    --no-owner \
    --no-privileges \
    "$BACKUP_FILE"

echo "Database restored successfully to: $TARGET_DB"
```

### Disaster Recovery Plan

**RTO (Recovery Time Objective):** 4 hours
**RPO (Recovery Point Objective):** 1 hour

**Recovery steps:**

1. **Assess damage and activate DR team**
2. **Restore database from latest backup**
3. **Deploy application to DR environment**  
4. **Update DNS to point to DR environment**
5. **Verify system functionality**
6. **Communicate status to stakeholders**

---

## Scaling Considerations

### Horizontal Scaling

**Load balancer configuration (nginx):**

```nginx
# /etc/nginx/sites-available/nexum-api
upstream nexum_backend {
    least_conn;
    server nexum-api-1:8090 max_fails=3 fail_timeout=30s;
    server nexum-api-2:8090 max_fails=3 fail_timeout=30s;
    server nexum-api-3:8090 max_fails=3 fail_timeout=30s;
}

server {
    listen 443 ssl http2;
    server_name api.yourbank.com;
    
    # SSL configuration
    ssl_certificate /etc/ssl/certs/yourbank.com.pem;
    ssl_certificate_key /etc/ssl/private/yourbank.com.key;
    
    # Proxy configuration
    location / {
        proxy_pass http://nexum_backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Timeouts
        proxy_connect_timeout 5s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
        
        # Health checks
        proxy_next_upstream error timeout invalid_header http_500 http_502 http_503 http_504;
    }
    
    # Health check endpoint
    location /health {
        access_log off;
        proxy_pass http://nexum_backend;
    }
}
```

### Database Scaling

**Read replica configuration:**

```yaml
# docker-compose.production.yml (database section)
services:
  postgres-primary:
    image: postgres:15
    environment:
      - POSTGRES_DB=nexum_production
      - POSTGRES_USER=nexum_prod
      - POSTGRES_PASSWORD=${DB_PASSWORD}
      - POSTGRES_REPLICATION_USER=replicator
      - POSTGRES_REPLICATION_PASSWORD=${REPLICATION_PASSWORD}
    volumes:
      - postgres_primary_data:/var/lib/postgresql/data
      - ./postgresql-primary.conf:/etc/postgresql/postgresql.conf
    command: postgres -c config_file=/etc/postgresql/postgresql.conf
    
  postgres-replica:
    image: postgres:15
    environment:
      - PGUSER=nexum_prod
      - POSTGRES_PASSWORD=${DB_PASSWORD}
      - PGPASSWORD=${REPLICATION_PASSWORD}
    volumes:
      - postgres_replica_data:/var/lib/postgresql/data
    command: |
      bash -c "
      if [ ! -f /var/lib/postgresql/data/recovery.conf ]; then
        pg_basebackup -h postgres-primary -D /var/lib/postgresql/data -U replicator -v -P -W
        echo \"standby_mode = 'on'\" >> /var/lib/postgresql/data/recovery.conf
        echo \"primary_conninfo = 'host=postgres-primary port=5432 user=replicator'\" >> /var/lib/postgresql/data/recovery.conf
      fi
      postgres
      "
```

**Read/write splitting:**

```python
class DatabaseRouter:
    """Route read queries to replica, writes to primary"""
    
    def __init__(self, primary_url, replica_urls):
        self.primary = PostgreSQLStorage(primary_url)
        self.replicas = [PostgreSQLStorage(url) for url in replica_urls]
        self.replica_index = 0
    
    def get_connection(self, operation_type="read"):
        """Get appropriate database connection"""
        if operation_type in ["write", "transaction"]:
            return self.primary
        else:
            # Round-robin read replicas
            replica = self.replicas[self.replica_index]
            self.replica_index = (self.replica_index + 1) % len(self.replicas)
            return replica
```

### Auto-scaling with Kubernetes

```yaml
# kubernetes/hpa.yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: nexum-api-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: nexum-api
  minReplicas: 3
  maxReplicas: 20
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
  - type: Resource
    resource:
      name: memory
      target:
        type: Utilization
        averageUtilization: 80
  behavior:
    scaleDown:
      stabilizationWindowSeconds: 300
      policies:
      - type: Percent
        value: 10
        periodSeconds: 60
    scaleUp:
      stabilizationWindowSeconds: 60
      policies:
      - type: Percent
        value: 50
        periodSeconds: 60
```

---

## Infrastructure as Code

### Terraform Configuration

```hcl
# main.tf
provider "aws" {
  region = var.aws_region
}

# VPC and networking
resource "aws_vpc" "nexum_vpc" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = {
    Name = "nexum-vpc"
  }
}

resource "aws_subnet" "nexum_private" {
  count             = 2
  vpc_id            = aws_vpc.nexum_vpc.id
  cidr_block        = "10.0.${count.index + 1}.0/24"
  availability_zone = data.aws_availability_zones.available.names[count.index]

  tags = {
    Name = "nexum-private-${count.index + 1}"
  }
}

resource "aws_subnet" "nexum_public" {
  count                   = 2
  vpc_id                  = aws_vpc.nexum_vpc.id
  cidr_block              = "10.0.${count.index + 10}.0/24"
  availability_zone       = data.aws_availability_zones.available.names[count.index]
  map_public_ip_on_launch = true

  tags = {
    Name = "nexum-public-${count.index + 1}"
  }
}

# RDS PostgreSQL
resource "aws_db_instance" "nexum_db" {
  identifier = "nexum-production"
  
  engine         = "postgres"
  engine_version = "15.4"
  instance_class = "db.r6g.large"
  
  allocated_storage     = 100
  max_allocated_storage = 1000
  storage_type          = "gp3"
  storage_encrypted     = true
  
  db_name  = "nexum_production"
  username = "nexum_prod"
  password = var.db_password
  
  vpc_security_group_ids = [aws_security_group.nexum_db.id]
  db_subnet_group_name   = aws_db_subnet_group.nexum_db.name
  
  backup_retention_period = 30
  backup_window          = "03:00-04:00"
  maintenance_window     = "sun:04:00-sun:05:00"
  
  monitoring_interval = 60
  monitoring_role_arn = aws_iam_role.nexum_monitoring.arn
  
  tags = {
    Name = "nexum-production-db"
  }
}

# ECS Fargate for application
resource "aws_ecs_cluster" "nexum_cluster" {
  name = "nexum-production"
  
  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}

resource "aws_ecs_task_definition" "nexum_api" {
  family                   = "nexum-api"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = 1024
  memory                   = 2048
  execution_role_arn       = aws_iam_role.nexum_execution.arn
  task_role_arn           = aws_iam_role.nexum_task.arn
  
  container_definitions = jsonencode([
    {
      name  = "nexum-api"
      image = "${var.ecr_repository_url}:latest"
      
      portMappings = [
        {
          containerPort = 8090
          protocol     = "tcp"
        }
      ]
      
      environment = [
        {
          name  = "NEXUM_DATABASE_URL"
          value = "postgresql://${aws_db_instance.nexum_db.username}:${var.db_password}@${aws_db_instance.nexum_db.endpoint}:5432/${aws_db_instance.nexum_db.db_name}"
        }
      ]
      
      secrets = [
        {
          name      = "NEXUM_JWT_SECRET"
          valueFrom = aws_ssm_parameter.jwt_secret.arn
        },
        {
          name      = "NEXUM_ENCRYPTION_MASTER_KEY"
          valueFrom = aws_ssm_parameter.encryption_key.arn
        }
      ]
      
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.nexum_api.name
          awslogs-region        = var.aws_region
          awslogs-stream-prefix = "ecs"
        }
      }
      
      healthCheck = {
        command = ["CMD-SHELL", "curl -f http://localhost:8090/health || exit 1"]
        interval = 30
        timeout = 10
        retries = 3
        startPeriod = 60
      }
    }
  ])
}

# Application Load Balancer
resource "aws_lb" "nexum_alb" {
  name               = "nexum-production-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.nexum_alb.id]
  subnets           = aws_subnet.nexum_public[*].id
  
  enable_deletion_protection = true
  
  tags = {
    Name = "nexum-production-alb"
  }
}

# Auto Scaling
resource "aws_appautoscaling_target" "nexum_target" {
  max_capacity       = 20
  min_capacity       = 3
  resource_id        = "service/${aws_ecs_cluster.nexum_cluster.name}/${aws_ecs_service.nexum_api.name}"
  scalable_dimension = "ecs:service:DesiredCount"
  service_namespace  = "ecs"
}

resource "aws_appautoscaling_policy" "nexum_up" {
  name               = "nexum-scale-up"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.nexum_target.resource_id
  scalable_dimension = aws_appautoscaling_target.nexum_target.scalable_dimension
  service_namespace  = aws_appautoscaling_target.nexum_target.service_namespace
  
  target_tracking_scaling_policy_configuration {
    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageCPUUtilization"
    }
    target_value = 70.0
  }
}
```

This comprehensive deployment guide provides production-ready patterns for deploying Nexum core banking system across various environments and infrastructure configurations.