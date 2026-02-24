#!/usr/bin/env python3
"""
Shared client/customer fixture for Bastion + Nexum.
Both seed scripts should import from here to keep IDs aligned.

Usage:
    from shared_clients import SENDERS, RECEIVERS, ALL_CLIENTS
"""

import random
import json

# Fix seed for reproducible client generation
random.seed(42)

COUNTRIES_WITH_NAMES = {
    "US": {
        "first": ["James", "Sarah", "Michael", "Emily", "Robert", "Jennifer", "David", "Jessica", "Daniel", "Ashley",
                   "Christopher", "Amanda", "Matthew", "Stephanie", "Andrew", "Nicole", "Joshua", "Elizabeth", "Brandon", "Megan",
                   "Tyler", "Lauren", "Kevin", "Samantha", "Justin", "Rachel", "Ryan", "Kayla", "Jacob", "Hannah"],
        "last": ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis", "Rodriguez", "Martinez",
                 "Wilson", "Anderson", "Taylor", "Thomas", "Hernandez", "Moore", "Jackson", "Martin", "Lee", "Thompson"],
        "cities": ["New York", "Los Angeles", "Chicago", "Houston", "Phoenix", "Philadelphia", "San Francisco", "Seattle", "Denver", "Miami"],
        "phone_prefix": "+1",
        "email_domains": ["gmail.com", "yahoo.com", "outlook.com"],
    },
    "GB": {
        "first": ["Oliver", "Charlotte", "Harry", "Amelia", "George", "Isla", "Jack", "Mia", "William", "Sophia"],
        "last": ["Smith", "Jones", "Williams", "Brown", "Taylor", "Davies", "Evans", "Wilson", "Thomas", "Roberts"],
        "cities": ["London", "Manchester", "Birmingham", "Leeds", "Liverpool"],
        "phone_prefix": "+44",
        "email_domains": ["gmail.com", "outlook.co.uk", "bt.com"],
    },
    "DE": {
        "first": ["Hans", "Anna", "Klaus", "Petra", "Stefan", "Monika", "Wolfgang", "Sabine", "Thomas", "Ursula"],
        "last": ["Müller", "Schmidt", "Schneider", "Fischer", "Weber", "Meyer", "Wagner", "Becker", "Schulz", "Hoffmann"],
        "cities": ["Berlin", "Munich", "Frankfurt", "Hamburg", "Cologne"],
        "phone_prefix": "+49",
        "email_domains": ["gmail.com", "web.de", "gmx.de"],
    },
    "FR": {
        "first": ["Jean", "Sophie", "Pierre", "Marie", "François", "Isabelle", "Michel", "Catherine", "Philippe", "Nathalie"],
        "last": ["Martin", "Bernard", "Dubois", "Thomas", "Robert", "Richard", "Petit", "Durand", "Leroy", "Moreau"],
        "cities": ["Paris", "Lyon", "Marseille", "Toulouse", "Nice"],
        "phone_prefix": "+33",
        "email_domains": ["gmail.com", "orange.fr", "free.fr"],
    },
    "JP": {
        "first": ["Kenji", "Yuki", "Takeshi", "Sakura", "Hiroshi", "Aiko", "Akira", "Haruki", "Satoshi", "Mei"],
        "last": ["Sato", "Suzuki", "Takahashi", "Tanaka", "Watanabe", "Ito", "Yamamoto", "Nakamura", "Kobayashi", "Kato"],
        "cities": ["Tokyo", "Osaka", "Kyoto", "Yokohama", "Nagoya"],
        "phone_prefix": "+81",
        "email_domains": ["gmail.com", "yahoo.co.jp"],
    },
    "IN": {
        "first": ["Raj", "Priya", "Vikram", "Deepa", "Arjun", "Sunita", "Anil", "Kavita", "Suresh", "Anjali"],
        "last": ["Sharma", "Patel", "Singh", "Kumar", "Gupta", "Reddy", "Nair", "Bose", "Das", "Chopra"],
        "cities": ["Mumbai", "Delhi", "Bangalore", "Chennai", "Hyderabad"],
        "phone_prefix": "+91",
        "email_domains": ["gmail.com", "yahoo.in", "rediffmail.com"],
    },
    "BR": {
        "first": ["João", "Ana", "Carlos", "Mariana", "Pedro", "Julia", "Lucas", "Fernanda", "Rafael", "Camila"],
        "last": ["Silva", "Santos", "Oliveira", "Souza", "Rodrigues", "Ferreira", "Alves", "Pereira", "Lima", "Gomes"],
        "cities": ["São Paulo", "Rio de Janeiro", "Brasilia", "Salvador", "Curitiba"],
        "phone_prefix": "+55",
        "email_domains": ["gmail.com", "uol.com.br", "hotmail.com"],
    },
    "AU": {
        "first": ["Liam", "Olivia", "Noah", "Emma", "Jack", "Ava", "Thomas", "Chloe", "Mason", "Sophie"],
        "last": ["Smith", "Jones", "Williams", "Brown", "Wilson", "Taylor", "Johnson", "White", "Martin", "Anderson"],
        "cities": ["Sydney", "Melbourne", "Brisbane", "Perth", "Adelaide"],
        "phone_prefix": "+61",
        "email_domains": ["gmail.com", "outlook.com.au", "bigpond.com"],
    },
    "KR": {
        "first": ["Minjun", "Seoyeon", "Seongjin", "Jiwoo", "Jihun", "Chaeyoung", "Junwoo", "Soyeon", "Dokyun", "Hayeon"],
        "last": ["Kim", "Lee", "Park", "Choi", "Jung", "Kang", "Cho", "Yoon", "Jang", "Lim"],
        "cities": ["Seoul", "Busan", "Incheon", "Daegu", "Daejeon"],
        "phone_prefix": "+82",
        "email_domains": ["gmail.com", "naver.com", "daum.net"],
    },
    "NG": {
        "first": ["Oluwaseun", "Amara", "Chukwuemeka", "Ngozi", "Obinna", "Chidinma", "Emeka", "Funke", "Tunde", "Blessing"],
        "last": ["Adeyemi", "Okafor", "Ibrahim", "Mohammed", "Ogundimu", "Eze", "Nwachukwu", "Balogun", "Abubakar", "Olawale"],
        "cities": ["Lagos", "Abuja", "Port Harcourt", "Kano", "Ibadan"],
        "phone_prefix": "+234",
        "email_domains": ["gmail.com", "yahoo.com"],
    },
}

RECEIVER_NAMES = [
    ("Amazon Marketplace", "US"), ("Walmart Stores", "US"), ("Target Corp", "US"),
    ("Tesco PLC", "GB"), ("ASOS Holdings", "GB"),
    ("Lidl Stiftung", "DE"), ("Zalando SE", "DE"),
    ("Carrefour SA", "FR"), ("LVMH Group", "FR"),
    ("Sony Group", "JP"), ("Toyota Financial", "JP"),
    ("Reliance Industries", "IN"), ("Tata Consultancy", "IN"),
    ("MercadoLibre", "BR"), ("Petrobras Trading", "BR"),
    ("Samsung Electronics", "KR"), ("Hyundai Motor Finance", "KR"),
    ("Woolworths Group", "AU"), ("BHP Group", "AU"),
    ("Dangote Industries", "NG"), ("MTN Nigeria", "NG"),
    ("Alibaba Cloud", "US"), ("Stripe Payments", "US"),
    ("PayPal Holdings", "US"), ("Shopify Inc", "US"),
    ("Revolut Ltd", "GB"), ("Wise PLC", "GB"),
    ("SAP SE", "DE"), ("Adidas AG", "DE"),
    ("TotalEnergies SE", "FR"),
]

RISK_WEIGHTS = {"low": 60, "medium": 20, "high": 12, "critical": 8}
KYC_LEVELS = {
    "low": ["full", "enhanced"],
    "medium": ["enhanced", "basic"],
    "high": ["basic", "basic"],
    "critical": ["basic", "basic"],
}

NUM_SENDERS = 120
NUM_RECEIVERS = 30


def _gen_client(idx, is_receiver=False):
    prefix = "recv" if is_receiver else "cust"
    ext_id = f"{prefix}_{idx:03d}"

    if is_receiver and idx <= len(RECEIVER_NAMES):
        name, country = RECEIVER_NAMES[idx - 1]
        email_user = name.lower().replace(" ", ".").replace(",", "")
        info = COUNTRIES_WITH_NAMES.get(country, COUNTRIES_WITH_NAMES["US"])
        domain = random.choice(info["email_domains"])
        risk = random.choices(["low", "medium", "high", "critical"], weights=[30, 30, 25, 15])[0]
    else:
        country = random.choice(list(COUNTRIES_WITH_NAMES.keys()))
        info = COUNTRIES_WITH_NAMES[country]
        first = random.choice(info["first"])
        last = random.choice(info["last"])
        name = f"{first} {last}"
        email_user = f"{first.lower()}.{last.lower()}"
        domain = random.choice(info["email_domains"])
        risk = random.choices(list(RISK_WEIGHTS.keys()), weights=list(RISK_WEIGHTS.values()))[0]

    import re
    email_user_clean = re.sub(r'[^a-z0-9.]', '', email_user.lower())
    city = random.choice(info.get("cities", ["Unknown"]))
    phone_pre = info.get("phone_prefix", "+1")
    phone = f"{phone_pre}-{random.randint(100,999)}-{random.randint(1000,9999)}"
    kyc = random.choice(KYC_LEVELS[risk])

    return {
        "external_id": ext_id,
        "full_name": name,
        "email": f"{email_user_clean}@{domain}",
        "phone": phone,
        "city": city,
        "country": country,
        "risk_rating": risk,
        "kyc_level": kyc,
        "address": f"{random.randint(1, 999)} {city} Street, {city}, {country}",
        "id_document": f"{ext_id.upper()}-{random.randint(100000, 999999)}",
        "client_type": "institution" if is_receiver else "individual",
    }


# Generate once with fixed seed
SENDERS = [_gen_client(i + 1, is_receiver=False) for i in range(NUM_SENDERS)]
RECEIVERS = [_gen_client(i + 1, is_receiver=True) for i in range(NUM_RECEIVERS)]
ALL_CLIENTS = SENDERS + RECEIVERS


if __name__ == "__main__":
    print(f"Generated {len(SENDERS)} senders + {len(RECEIVERS)} receivers = {len(ALL_CLIENTS)} total")
    print(f"\nFirst 5 senders:")
    for c in SENDERS[:5]:
        print(f"  {c['external_id']}: {c['full_name']} ({c['country']}, {c['risk_rating']})")
    print(f"\nFirst 5 receivers:")
    for c in RECEIVERS[:5]:
        print(f"  {c['external_id']}: {c['full_name']} ({c['country']}, {c['risk_rating']})")
