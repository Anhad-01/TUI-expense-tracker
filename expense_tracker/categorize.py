from __future__ import annotations

import re


DEFAULT_CATEGORY = "Uncategorized"

CATEGORY_RULES: list[tuple[str, str]] = [
    (r"\b(rapido|uber|ola|namma yatri)\b", "Transport"),
    (r"\b(delhi metro|metro|rail|irctc)\b", "Transit"),
    (r"\b(spotify|netflix|prime|hotstar|youtube premium)\b", "Subscriptions"),
    (r"\b(amazon|flipkart|myntra|ajio|nykaa)\b", "Shopping"),
    (r"\b(zomato|swiggy|burger king|mcdonald|restaurant|cafe|pizza)\b", "Food"),
    (r"\b(airtel|jio|vi|bsnl|recharge|electricity|water|gas)\b", "Utilities"),
    (r"\b(pharmacy|apollo|medplus|hospital|clinic|doctor)\b", "Health"),
    (r"\b(rent|maintenance|society)\b", "Housing"),
    (r"\b(salary|refund|cashback|interest)\b", "Income"),
]


def categorize(transaction: str) -> str:
    value = transaction or ""
    for pattern, category in CATEGORY_RULES:
        if re.search(pattern, value, re.IGNORECASE):
            return category
    return DEFAULT_CATEGORY

