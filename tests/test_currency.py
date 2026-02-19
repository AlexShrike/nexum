"""
Test suite for currency module

Tests Money class, currency conversion, and proper Decimal handling.
All monetary calculations must use Decimal precision.
"""

import pytest
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, timezone

from core_banking.currency import (
    Money, Currency, ExchangeRate, CurrencyConverter,
    decimal_from_string, validate_decimal_precision
)


class TestMoney:
    """Test Money class operations"""
    
    def test_money_creation(self):
        """Test Money object creation and validation"""
        # Valid creation
        money = Money(Decimal('100.50'), Currency.USD)
        assert money.amount == Decimal('100.50')
        assert money.currency == Currency.USD
        
        # Test automatic rounding to currency precision
        money_rounded = Money(Decimal('100.555'), Currency.USD)  # 2 decimal places for USD
        assert money_rounded.amount == Decimal('100.56')  # Rounded up
        
        # Test JPY (0 decimal places)
        money_jpy = Money(Decimal('100.7'), Currency.JPY)
        assert money_jpy.amount == Decimal('101')  # Rounded to nearest yen
    
    def test_money_arithmetic(self):
        """Test Money arithmetic operations"""
        money1 = Money(Decimal('100.50'), Currency.USD)
        money2 = Money(Decimal('50.25'), Currency.USD)
        
        # Addition
        result = money1 + money2
        assert result.amount == Decimal('150.75')
        assert result.currency == Currency.USD
        
        # Subtraction
        result = money1 - money2
        assert result.amount == Decimal('50.25')
        assert result.currency == Currency.USD
        
        # Multiplication
        result = money1 * Decimal('2')
        assert result.amount == Decimal('201.00')
        assert result.currency == Currency.USD
        
        # Division
        result = money1 / Decimal('2')
        assert result.amount == Decimal('50.25')
        assert result.currency == Currency.USD
        
        # Negation
        result = -money1
        assert result.amount == Decimal('-100.50')
        assert result.currency == Currency.USD
        
        # Absolute value
        negative_money = Money(Decimal('-50.00'), Currency.USD)
        result = abs(negative_money)
        assert result.amount == Decimal('50.00')
        assert result.currency == Currency.USD
    
    def test_money_comparison(self):
        """Test Money comparison operations"""
        money1 = Money(Decimal('100.00'), Currency.USD)
        money2 = Money(Decimal('50.00'), Currency.USD)
        money3 = Money(Decimal('100.00'), Currency.USD)
        
        # Equality
        assert money1 == money3
        assert money1 != money2
        
        # Comparison
        assert money1 > money2
        assert money2 < money1
        assert money1 >= money3
        assert money1 <= money3
    
    def test_money_currency_mismatch(self):
        """Test that operations with different currencies raise errors"""
        usd_money = Money(Decimal('100.00'), Currency.USD)
        eur_money = Money(Decimal('100.00'), Currency.EUR)
        
        with pytest.raises(ValueError, match="Cannot add USD and EUR"):
            usd_money + eur_money
        
        with pytest.raises(ValueError, match="Cannot subtract EUR from USD"):
            usd_money - eur_money
        
        with pytest.raises(ValueError, match="Cannot compare USD and EUR"):
            usd_money < eur_money
    
    def test_money_state_checks(self):
        """Test Money state checking methods"""
        zero_money = Money(Decimal('0.00'), Currency.USD)
        positive_money = Money(Decimal('100.50'), Currency.USD)
        negative_money = Money(Decimal('-50.25'), Currency.USD)
        
        # Zero checks
        assert zero_money.is_zero()
        assert not positive_money.is_zero()
        assert not negative_money.is_zero()
        
        # Positive checks
        assert not zero_money.is_positive()
        assert positive_money.is_positive()
        assert not negative_money.is_positive()
        
        # Negative checks
        assert not zero_money.is_negative()
        assert not positive_money.is_negative()
        assert negative_money.is_negative()
    
    def test_money_string_formatting(self):
        """Test Money string representation"""
        usd_money = Money(Decimal('1234.56'), Currency.USD)
        assert usd_money.to_string() == "USD 1,234.56"
        
        jpy_money = Money(Decimal('1234'), Currency.JPY)
        assert jpy_money.to_string() == "JPY 1,234"
        
        large_amount = Money(Decimal('1234567.89'), Currency.USD)
        assert large_amount.to_string() == "USD 1,234,567.89"


class TestExchangeRate:
    """Test ExchangeRate functionality"""
    
    def test_exchange_rate_creation(self):
        """Test exchange rate creation and validation"""
        rate = ExchangeRate(
            from_currency=Currency.USD,
            to_currency=Currency.EUR,
            bid=Decimal('0.85'),
            ask=Decimal('0.87'),
            mid=Decimal('0.86'),
            timestamp=datetime.now(timezone.utc)
        )
        
        assert rate.from_currency == Currency.USD
        assert rate.to_currency == Currency.EUR
        assert rate.bid == Decimal('0.85')
        assert rate.ask == Decimal('0.87')
        assert rate.mid == Decimal('0.86')
    
    def test_exchange_rate_decimal_conversion(self):
        """Test that string values are converted to Decimal"""
        rate = ExchangeRate(
            from_currency=Currency.USD,
            to_currency=Currency.EUR,
            bid="0.85",  # String input
            ask="0.87",  # String input  
            mid="0.86",  # String input
            timestamp=datetime.now(timezone.utc)
        )
        
        # Should be converted to Decimal
        assert isinstance(rate.bid, Decimal)
        assert isinstance(rate.ask, Decimal)
        assert isinstance(rate.mid, Decimal)


class TestCurrencyConverter:
    """Test CurrencyConverter functionality"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.converter = CurrencyConverter()
        
        # Set up USD/EUR exchange rate
        self.usd_eur_rate = ExchangeRate(
            from_currency=Currency.USD,
            to_currency=Currency.EUR,
            bid=Decimal('0.85'),
            ask=Decimal('0.87'),
            mid=Decimal('0.86'),
            timestamp=datetime.now(timezone.utc)
        )
        self.converter.set_rate(self.usd_eur_rate)
    
    def test_same_currency_conversion(self):
        """Test conversion between same currency"""
        usd_money = Money(Decimal('100.00'), Currency.USD)
        result = self.converter.convert(usd_money, Currency.USD)
        
        assert result == usd_money
        assert result.currency == Currency.USD
    
    def test_currency_conversion_with_mid_rate(self):
        """Test currency conversion using mid rate"""
        usd_money = Money(Decimal('100.00'), Currency.USD)
        eur_result = self.converter.convert(usd_money, Currency.EUR, use_mid_rate=True)
        
        expected_amount = Decimal('100.00') * Decimal('0.86')
        assert eur_result.amount == expected_amount
        assert eur_result.currency == Currency.EUR
    
    def test_currency_conversion_with_bid_rate(self):
        """Test currency conversion using bid rate"""
        usd_money = Money(Decimal('100.00'), Currency.USD)
        eur_result = self.converter.convert(usd_money, Currency.EUR, use_mid_rate=False)
        
        expected_amount = Decimal('100.00') * Decimal('0.85')  # Bid rate
        assert eur_result.amount == expected_amount
        assert eur_result.currency == Currency.EUR
    
    def test_reverse_rate_creation(self):
        """Test that reverse rates are automatically created"""
        # Should be able to convert EUR back to USD
        eur_money = Money(Decimal('86.00'), Currency.EUR)
        usd_result = self.converter.convert(eur_money, Currency.USD, use_mid_rate=True)
        
        # Reverse rate should be 1/0.86 ≈ 1.162791
        expected_amount = Decimal('86.00') / Decimal('0.86')
        assert abs(usd_result.amount - expected_amount) < Decimal('0.01')
        assert usd_result.currency == Currency.USD
    
    def test_conversion_with_no_rate(self):
        """Test conversion when no exchange rate is available"""
        gbp_money = Money(Decimal('100.00'), Currency.GBP)
        
        with pytest.raises(ValueError, match="No exchange rate available"):
            self.converter.convert(gbp_money, Currency.USD)
    
    def test_get_all_rates(self):
        """Test getting all exchange rates"""
        all_rates = self.converter.get_all_rates()
        
        # Should have both USD->EUR and EUR->USD rates
        assert len(all_rates) == 2
        assert (Currency.USD, Currency.EUR) in all_rates
        assert (Currency.EUR, Currency.USD) in all_rates


class TestUtilityFunctions:
    """Test utility functions for decimal handling"""
    
    def test_decimal_from_string_valid(self):
        """Test decimal conversion from valid strings"""
        # Basic decimal
        assert decimal_from_string("123.45") == Decimal("123.45")
        
        # With comma as thousands separator
        assert decimal_from_string("1,234.56") == Decimal("1234.56")
        
        # European format (comma as decimal separator)
        assert decimal_from_string("123,45") == Decimal("123.45")
        
        # With currency symbols (should be stripped)
        assert decimal_from_string("$1,234.56") == Decimal("1234.56")
        assert decimal_from_string("€123,45") == Decimal("123.45")
        
        # Negative values
        assert decimal_from_string("-123.45") == Decimal("-123.45")
    
    def test_decimal_from_string_invalid(self):
        """Test decimal conversion from invalid strings"""
        with pytest.raises(ValueError):
            decimal_from_string("")
        
        with pytest.raises(ValueError):
            decimal_from_string("not_a_number")
        
        with pytest.raises(ValueError):
            decimal_from_string(None)
    
    def test_validate_decimal_precision(self):
        """Test decimal precision validation"""
        # USD (2 decimal places)
        value = Decimal('123.456')
        result = validate_decimal_precision(value, Currency.USD)
        assert result == Decimal('123.46')  # Rounded up
        
        # JPY (0 decimal places)
        value = Decimal('123.7')
        result = validate_decimal_precision(value, Currency.JPY)
        assert result == Decimal('124')  # Rounded up
        
        # Already correct precision
        value = Decimal('123.45')
        result = validate_decimal_precision(value, Currency.USD)
        assert result == Decimal('123.45')  # Unchanged


class TestCurrencyPrecisionRules:
    """Test currency-specific precision rules"""
    
    def test_usd_precision(self):
        """Test USD 2-decimal precision"""
        money = Money(Decimal('123.456'), Currency.USD)
        assert money.amount == Decimal('123.46')
    
    def test_eur_precision(self):
        """Test EUR 2-decimal precision"""
        money = Money(Decimal('123.456'), Currency.EUR)
        assert money.amount == Decimal('123.46')
    
    def test_jpy_precision(self):
        """Test JPY 0-decimal precision"""
        money = Money(Decimal('123.7'), Currency.JPY)
        assert money.amount == Decimal('124')
        
        money2 = Money(Decimal('123.4'), Currency.JPY)
        assert money2.amount == Decimal('123')
    
    def test_rounding_method(self):
        """Test that ROUND_HALF_UP is used consistently"""
        # Test exact half - should round up
        money = Money(Decimal('123.455'), Currency.USD)
        assert money.amount == Decimal('123.46')  # Half rounded up
        
        money_jpy = Money(Decimal('123.5'), Currency.JPY)
        assert money_jpy.amount == Decimal('124')  # Half rounded up


class TestMoneyEdgeCases:
    """Test edge cases and error conditions"""
    
    def test_very_large_amounts(self):
        """Test handling of very large monetary amounts"""
        large_amount = Money(Decimal('999999999999999.99'), Currency.USD)
        assert large_amount.amount == Decimal('999999999999999.99')
        
        # Test arithmetic with large amounts
        result = large_amount + Money(Decimal('0.01'), Currency.USD)
        assert result.amount == Decimal('1000000000000000.00')
    
    def test_very_small_amounts(self):
        """Test handling of very small monetary amounts"""
        small_amount = Money(Decimal('0.001'), Currency.USD)
        assert small_amount.amount == Decimal('0.00')  # Rounded to currency precision
        
        small_amount = Money(Decimal('0.006'), Currency.USD)
        assert small_amount.amount == Decimal('0.01')  # Rounded up
    
    def test_zero_amounts(self):
        """Test handling of zero amounts"""
        zero = Money(Decimal('0'), Currency.USD)
        assert zero.is_zero()
        assert not zero.is_positive()
        assert not zero.is_negative()
        
        # Arithmetic with zero
        money = Money(Decimal('100.00'), Currency.USD)
        assert money + zero == money
        assert money - zero == money
        assert zero * Decimal('100') == zero
    
    def test_negative_amounts(self):
        """Test handling of negative amounts"""
        negative = Money(Decimal('-100.50'), Currency.USD)
        assert negative.is_negative()
        assert not negative.is_positive()
        assert not negative.is_zero()
        
        # Test absolute value
        positive = abs(negative)
        assert positive.is_positive()
        assert positive.amount == Decimal('100.50')


if __name__ == "__main__":
    pytest.main([__file__])