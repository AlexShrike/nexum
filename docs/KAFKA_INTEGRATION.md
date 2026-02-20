# Kafka Integration for Bastion Fraud Detection

This document describes the Kafka-based integration between Nexum (core banking system) and Bastion (fraud detection system).

## Overview

Nexum publishes transaction and customer events to Kafka topics that Bastion consumes for real-time fraud detection. Bastion then publishes fraud decisions and alerts back to Nexum for processing.

## Architecture

```
┌─────────────────┐    Kafka Topics    ┌─────────────────┐
│     Nexum       │───────────────────▶│    Bastion      │
│  (Core Banking) │                    │ (Fraud Detection)│
│                 │◀───────────────────│                 │
└─────────────────┘                    └─────────────────┘
        │                                       │
        ▼                                       ▼
┌─────────────────┐                    ┌─────────────────┐
│   Transaction   │                    │ Fraud Decisions │
│   Processing    │                    │   & Alerts      │
└─────────────────┘                    └─────────────────┘
```

## Kafka Topics

### Outbound Topics (Nexum → Bastion)

#### `nexum.transactions`
Transaction events published when transactions are posted.

**Schema:**
```json
{
  "event_type": "transaction.processed",
  "transaction_id": "string",
  "amount": "decimal_string",
  "currency": "string",
  "from_account_id": "string",
  "to_account_id": "string", 
  "customer_id": "string",
  "transaction_type": "string",
  "channel": "string",
  "description": "string",
  "timestamp": "iso8601",
  "metadata": {
    "device_id": "string",
    "ip_address": "string",
    "user_agent": "string",
    "reference": "string"
  }
}
```

**Transaction Types:**
- `DEPOSIT`
- `WITHDRAWAL` 
- `TRANSFER`
- `PAYMENT`
- `FEE`

**Channels:**
- `ONLINE`
- `MOBILE`
- `ATM`
- `BRANCH`
- `PHONE`

#### `nexum.customers`
Customer events published when customers are created or updated.

**Schema:**
```json
{
  "event_type": "customer.created|customer.updated",
  "customer_id": "string",
  "first_name": "string",
  "last_name": "string",
  "email": "string",
  "phone": "string",
  "kyc_status": "string",
  "kyc_tier": "string",
  "timestamp": "iso8601"
}
```

### Inbound Topics (Bastion → Nexum)

#### `bastion.fraud.decisions`
Fraud decisions published by Bastion after scoring transactions.

**Schema:**
```json
{
  "event_type": "fraud.decision",
  "transaction_id": "string",
  "score": "float",
  "decision": "string",
  "risk_level": "string",
  "reasons": ["string"],
  "features": {},
  "model_scores": {},
  "latency_ms": "float",
  "timestamp": "iso8601"
}
```

**Decisions:**
- `APPROVE` - Transaction approved
- `REVIEW` - Manual review required
- `BLOCK` - Transaction blocked

**Risk Levels:**
- `LOW`
- `MEDIUM` 
- `HIGH`
- `CRITICAL`

#### `bastion.fraud.alerts`
Pattern-based fraud alerts published by Bastion.

**Schema:**
```json
{
  "event_type": "fraud.alert",
  "alert_id": "string",
  "customer_id": "string",
  "alert_type": "string",
  "severity": "string",
  "description": "string",
  "related_transactions": ["string"],
  "timestamp": "iso8601"
}
```

**Alert Types:**
- `VELOCITY` - High transaction velocity
- `PATTERN` - Suspicious pattern detected
- `NETWORK` - Network-based risk
- `DEVICE` - Device-based risk

## Integration Components

### FraudEventBridge

The `FraudEventBridge` class handles the integration between Nexum's internal event system and Kafka:

```python
from core_banking.fraud_events import FraudEventBridge
from core_banking.kafka_integration import KafkaEventBus

# Create Kafka event bus
kafka_config = {
    'bootstrap.servers': 'localhost:9092'
}
event_bus = KafkaEventBus(**kafka_config)

# Create and start fraud bridge
bridge = FraudEventBridge(
    event_bus=event_bus,
    storage=storage,
    compliance_manager=compliance_manager
)
bridge.start()
```

### Event Flow

1. **Transaction Processing**: When a transaction is posted in Nexum, a `TRANSACTION_POSTED` event is emitted
2. **Event Bridge**: `FraudEventBridge` catches the event and publishes it to `nexum.transactions` topic
3. **Bastion Processing**: Bastion consumes the event, scores it, and publishes decisions/alerts
4. **Decision Handling**: Bridge consumes decisions and updates transaction metadata
5. **Compliance Integration**: For `REVIEW`/`BLOCK` decisions, compliance alerts are created

## Configuration

### Kafka Configuration

```python
kafka_config = {
    'bootstrap.servers': 'kafka1:9092,kafka2:9092,kafka3:9092',
    'security.protocol': 'SSL',
    'ssl.ca.location': '/path/to/ca-cert',
    'ssl.certificate.location': '/path/to/client-cert',
    'ssl.key.location': '/path/to/client-key'
}
```

### Consumer Groups

- **Bastion**: `bastion-fraud-detection`
- **Nexum**: `nexum-fraud-bridge`

## Error Handling

### Graceful Degradation

The integration is designed to degrade gracefully:

- **No Kafka**: Falls back to `LogEventBus` (logs events only)
- **Kafka Unavailable**: Queues events in memory and retries
- **Bastion Unavailable**: Transactions continue processing without fraud scoring
- **Invalid Events**: Logged and skipped, processing continues

### Monitoring

Monitor these metrics:

- **Event Publishing Rate**: Transactions/second published to Kafka
- **Consumer Lag**: Delay between publishing and consuming
- **Decision Latency**: Time from transaction to fraud decision
- **Error Rates**: Failed publishes/consumes per minute

## Testing

### Unit Tests

```bash
cd /Users/alexshrike/.openclaw/workspace/core-banking
python -m pytest tests/test_fraud_events.py -v
```

### Integration Tests

```bash
# Start Kafka (Docker Compose)
docker-compose up -d kafka

# Run integration tests
python -m pytest tests/integration/test_kafka_fraud.py -v
```

### Mock Mode

For development without Kafka:

```python
from core_banking.fraud_events import create_fraud_bridge
from core_banking.kafka_integration import InMemoryEventBus

# Use in-memory event bus for testing
bridge = create_fraud_bridge(InMemoryEventBus())
bridge.start()
```

## Security Considerations

### Data Privacy

- Customer PII is minimized in events
- Sensitive data is hashed/tokenized where possible
- All Kafka connections use SSL/TLS encryption

### Access Control

- Kafka topics use ACLs to restrict access
- Service accounts have minimal required permissions
- Authentication via SSL certificates or SASL

### Audit Trail

- All fraud decisions are logged in audit tables
- Event publishing/consuming is tracked
- Compliance alerts are created for blocked transactions

## Troubleshooting

### Common Issues

1. **Consumer Lag**: Check Kafka cluster health and consumer scaling
2. **Missing Decisions**: Verify Bastion consumer is running and healthy
3. **Schema Errors**: Validate event schemas match between systems
4. **Connection Failures**: Check network connectivity and SSL certificates

### Debugging

Enable debug logging:

```python
import logging
logging.getLogger('nexum.fraud_events').setLevel(logging.DEBUG)
logging.getLogger('confluent_kafka').setLevel(logging.DEBUG)
```

Check event bus stats:

```python
stats = bridge.get_stats()
print(f"Bridge running: {stats['running']}")
print(f"Event bus running: {stats['event_bus_running']}")
```

## Future Enhancements

- **Real-time Dashboards**: Monitor fraud decision rates and patterns
- **Dynamic Rules**: Update fraud rules without restarting services
- **ML Model Versioning**: Deploy new fraud models via Kafka metadata
- **Cross-Channel Correlation**: Link transactions across channels for better detection