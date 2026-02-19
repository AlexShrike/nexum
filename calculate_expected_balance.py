#!/usr/bin/env python3

from decimal import Decimal, getcontext
import math

# Set high precision
getcontext().prec = 28

def calculate_compound_interest():
    principal = Decimal('10000.00')
    
    # For 2% APY (what the test account actually has)
    apy_2_percent = Decimal('0.02')
    
    # For 5% APY (what the test expects) 
    apy_5_percent = Decimal('0.05')
    
    print("=== Compound Interest Calculations ===")
    
    # Method 1: Simple APY compounding (annual)
    print("\n--- Simple APY Compounding (Annual) ---")
    final_2_pct = principal * (Decimal('1') + apy_2_percent)
    final_5_pct = principal * (Decimal('1') + apy_5_percent)
    print(f"2% APY: ${final_2_pct:.2f}")
    print(f"5% APY: ${final_5_pct:.2f}")
    
    # Method 2: Daily compounding to achieve APY
    print("\n--- Daily Compounding to Achieve APY ---")
    
    # For 2% APY with daily compounding:
    # APY = (1 + r/365)^365 - 1
    # 0.02 = (1 + r/365)^365 - 1
    # r = 365 * ((1.02)^(1/365) - 1)
    
    nominal_rate_2_pct = 365 * ((Decimal('1.02') ** (Decimal('1')/Decimal('365'))) - Decimal('1'))
    daily_rate_2_pct = nominal_rate_2_pct / Decimal('365')
    
    nominal_rate_5_pct = 365 * ((Decimal('1.05') ** (Decimal('1')/Decimal('365'))) - Decimal('1'))
    daily_rate_5_pct = nominal_rate_5_pct / Decimal('365')
    
    print(f"2% APY -> Nominal rate: {nominal_rate_2_pct:.6f}, Daily rate: {daily_rate_2_pct:.8f}")
    print(f"5% APY -> Nominal rate: {nominal_rate_5_pct:.6f}, Daily rate: {daily_rate_5_pct:.8f}")
    
    # Calculate final balances with daily compounding
    final_2_pct_daily = principal * ((Decimal('1') + daily_rate_2_pct) ** Decimal('365'))
    final_5_pct_daily = principal * ((Decimal('1') + daily_rate_5_pct) ** Decimal('365'))
    
    print(f"2% APY with daily compounding: ${final_2_pct_daily:.2f}")
    print(f"5% APY with daily compounding: ${final_5_pct_daily:.2f}")
    
    # Method 3: Our system approach with 5% NOMINAL rate (monthly posting)
    print("\n--- Our System Approach with 5% NOMINAL Rate (Monthly Interest Posting) ---")
    
    # Simulate our system: daily accrual, monthly posting
    balance = principal
    daily_rate = Decimal('0.05') / Decimal('365')  # 5% nominal rate (not APY)
    
    for month in range(12):
        # Days in each month (2024 is leap year)
        days_in_month = [31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month]
        
        # Accrue daily interest
        monthly_interest = Decimal('0')
        for day in range(days_in_month):
            daily_interest = balance * daily_rate
            monthly_interest += daily_interest
        
        # Post monthly interest
        balance += monthly_interest
        print(f"Month {month + 1}: Balance = ${balance:.2f}, Interest = ${monthly_interest:.2f}")
    
    print(f"\nFinal balance after 12 months: ${balance:.2f}")
    print(f"Total interest earned: ${balance - principal:.2f}")
    
    # Method 4: Simple 5% nominal rate with exact daily compounding
    print("\n--- Simple 5% Nominal Rate with Daily Compounding ---")
    daily_rate_5pct_nominal = Decimal('0.05') / Decimal('365')
    final_5pct_nominal = principal * ((Decimal('1') + daily_rate_5pct_nominal) ** Decimal('365'))
    print(f"5% nominal rate with daily compounding: ${final_5pct_nominal:.2f}")
    print(f"Interest earned: ${final_5pct_nominal - principal:.2f}")

if __name__ == "__main__":
    calculate_compound_interest()