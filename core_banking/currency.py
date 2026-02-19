"""
Multi-Currency Support Module

Handles ISO 4217 currency codes, exchange rates, and proper Decimal precision
for financial calculations. NEVER uses float for monetary values.
"""

from decimal import Decimal, ROUND_HALF_UP, getcontext
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Optional
from enum import Enum
import re

# Set global decimal context for financial precision
getcontext().prec = 28  # High precision for financial calculations

class Currency(Enum):
    """ISO 4217 Currency Codes with precision info"""
    USD = ("USD", 2)  # US Dollar, 2 decimal places
    EUR = ("EUR", 2)  # Euro, 2 decimal places  
    GBP = ("GBP", 2)  # British Pound, 2 decimal places
    JPY = ("JPY", 0)  # Japanese Yen, 0 decimal places
    CAD = ("CAD", 2)  # Canadian Dollar, 2 decimal places
    CHF = ("CHF", 2)  # Swiss Franc, 2 decimal places
    
    def __init__(self, code: str, precision: int):
        self.code = code
        self.precision = precision

@dataclass(frozen=True)
class Money:
    """
    Immutable money representation with currency and proper precision.
    All monetary values MUST use this class or raw Decimal.
    """
    amount: Decimal
    currency: Currency
    
    def __post_init__(self):
        if not isinstance(self.amount, Decimal):
            # Convert to Decimal if not already, but log warning in production
            object.__setattr__(self, 'amount', Decimal(str(self.amount)))
        
        # Round to currency precision
        rounded = self.amount.quantize(
            Decimal('0.1') ** self.currency.precision,
            rounding=ROUND_HALF_UP
        )
        object.__setattr__(self, 'amount', rounded)
    
    def __add__(self, other: 'Money') -> 'Money':
        if self.currency != other.currency:
            raise ValueError(f"Cannot add {self.currency.code} and {other.currency.code}")
        return Money(self.amount + other.amount, self.currency)
    
    def __sub__(self, other: 'Money') -> 'Money':
        if self.currency != other.currency:
            raise ValueError(f"Cannot subtract {other.currency.code} from {self.currency.code}")
        return Money(self.amount - other.amount, self.currency)
    
    def __mul__(self, multiplier: Decimal) -> 'Money':
        if not isinstance(multiplier, Decimal):
            multiplier = Decimal(str(multiplier))
        return Money(self.amount * multiplier, self.currency)
    
    def __truediv__(self, divisor: Decimal) -> 'Money':
        if not isinstance(divisor, Decimal):
            divisor = Decimal(str(divisor))
        return Money(self.amount / divisor, self.currency)
    
    def __neg__(self) -> 'Money':
        return Money(-self.amount, self.currency)
    
    def __abs__(self) -> 'Money':
        return Money(abs(self.amount), self.currency)
    
    def __eq__(self, other) -> bool:
        if not isinstance(other, Money):
            return False
        return self.amount == other.amount and self.currency == other.currency
    
    def __lt__(self, other: 'Money') -> bool:
        if self.currency != other.currency:
            raise ValueError(f"Cannot compare {self.currency.code} and {other.currency.code}")
        return self.amount < other.amount
    
    def __le__(self, other: 'Money') -> bool:
        if self.currency != other.currency:
            raise ValueError(f"Cannot compare {self.currency.code} and {other.currency.code}")
        return self.amount <= other.amount
    
    def __gt__(self, other: 'Money') -> bool:
        if self.currency != other.currency:
            raise ValueError(f"Cannot compare {self.currency.code} and {other.currency.code}")
        return self.amount > other.amount
    
    def __ge__(self, other: 'Money') -> bool:
        if self.currency != other.currency:
            raise ValueError(f"Cannot compare {self.currency.code} and {other.currency.code}")
        return self.amount >= other.amount
    
    def is_zero(self) -> bool:
        """Check if amount is exactly zero"""
        return self.amount == Decimal('0')
    
    def is_positive(self) -> bool:
        """Check if amount is positive"""
        return self.amount > Decimal('0')
    
    def is_negative(self) -> bool:
        """Check if amount is negative"""
        return self.amount < Decimal('0')
    
    def to_string(self) -> str:
        """Format for display"""
        if self.currency.precision == 0:
            return f"{self.currency.code} {self.amount:,.0f}"
        else:
            return f"{self.currency.code} {self.amount:,.{self.currency.precision}f}"

@dataclass
class ExchangeRate:
    """Exchange rate with bid/ask spread"""
    from_currency: Currency
    to_currency: Currency
    bid: Decimal  # Rate for buying to_currency
    ask: Decimal  # Rate for selling to_currency
    mid: Decimal  # Mid-market rate
    timestamp: datetime
    
    def __post_init__(self):
        # Ensure all rates are Decimal
        for field in ['bid', 'ask', 'mid']:
            value = getattr(self, field)
            if not isinstance(value, Decimal):
                setattr(self, field, Decimal(str(value)))

class CurrencyConverter:
    """Handles currency conversion with proper precision and audit trail"""
    
    def __init__(self):
        self._rates: Dict[tuple, ExchangeRate] = {}
    
    def set_rate(self, rate: ExchangeRate) -> None:
        """Set exchange rate for currency pair"""
        key = (rate.from_currency, rate.to_currency)
        self._rates[key] = rate
        
        # Also set reverse rate
        if rate.mid > Decimal('0'):
            reverse_rate = ExchangeRate(
                from_currency=rate.to_currency,
                to_currency=rate.from_currency,
                bid=Decimal('1') / rate.ask,
                ask=Decimal('1') / rate.bid,
                mid=Decimal('1') / rate.mid,
                timestamp=rate.timestamp
            )
            reverse_key = (rate.to_currency, rate.from_currency)
            self._rates[reverse_key] = reverse_rate
    
    def get_rate(self, from_currency: Currency, to_currency: Currency) -> Optional[ExchangeRate]:
        """Get exchange rate for currency pair"""
        if from_currency == to_currency:
            return ExchangeRate(
                from_currency=from_currency,
                to_currency=to_currency,
                bid=Decimal('1'),
                ask=Decimal('1'),
                mid=Decimal('1'),
                timestamp=datetime.now(timezone.utc)
            )
        
        key = (from_currency, to_currency)
        return self._rates.get(key)
    
    def convert(self, money: Money, to_currency: Currency, use_mid_rate: bool = True) -> Money:
        """
        Convert money from one currency to another
        
        Args:
            money: Money to convert
            to_currency: Target currency
            use_mid_rate: If True, use mid rate; if False, use appropriate bid/ask
            
        Returns:
            Converted Money object
            
        Raises:
            ValueError: If no exchange rate available
        """
        if money.currency == to_currency:
            return money
        
        rate = self.get_rate(money.currency, to_currency)
        if not rate:
            raise ValueError(f"No exchange rate available for {money.currency.code} -> {to_currency.code}")
        
        if use_mid_rate:
            conversion_rate = rate.mid
        else:
            # Use bid rate (we're buying the target currency)
            conversion_rate = rate.bid
        
        converted_amount = money.amount * conversion_rate
        return Money(converted_amount, to_currency)
    
    def get_all_rates(self) -> Dict[tuple, ExchangeRate]:
        """Get all current exchange rates"""
        return self._rates.copy()

def decimal_from_string(value: str) -> Decimal:
    """
    Safely convert string to Decimal, handling common formats
    
    Args:
        value: String representation of number
        
    Returns:
        Decimal value
        
    Raises:
        ValueError: If string cannot be converted to valid Decimal
    """
    if not value or not isinstance(value, str):
        raise ValueError("Value must be a non-empty string")
    
    # Remove currency symbols and whitespace
    clean_value = re.sub(r'[^\d.,\-+]', '', value.strip())
    
    # Handle comma as decimal separator (European format)
    if ',' in clean_value and '.' in clean_value:
        # Both comma and dot - assume comma is thousands separator
        clean_value = clean_value.replace(',', '')
    elif ',' in clean_value and clean_value.count(',') == 1:
        # Single comma - could be decimal separator
        parts = clean_value.split(',')
        if len(parts[1]) <= 3:  # Likely decimal separator
            clean_value = clean_value.replace(',', '.')
        else:  # Likely thousands separator
            clean_value = clean_value.replace(',', '')
    
    try:
        return Decimal(clean_value)
    except:
        raise ValueError(f"Cannot convert '{value}' to Decimal")

def validate_decimal_precision(value: Decimal, currency: Currency) -> Decimal:
    """
    Validate and round decimal to currency precision
    
    Args:
        value: Decimal to validate
        currency: Currency defining precision
        
    Returns:
        Properly rounded Decimal
    """
    return value.quantize(
        Decimal('0.1') ** currency.precision,
        rounding=ROUND_HALF_UP
    )