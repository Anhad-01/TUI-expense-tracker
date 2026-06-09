from __future__ import annotations

import re


DEFAULT_CATEGORY = "Uncategorized"

CATEGORY_RULES: list[tuple[str, str]] = [
    (r"\b(rapido|uber|ola|namma yatri\delhi metro|metro)\b", "Transport"),
    (r"\b(blinkit|rail|irctc)\b", "Transit"),
    (r"\b(spotify|netflix|prime|hotstar|youtube premium)\b", "Subscriptions"),
    (r"\b(amazon|zudio|max|trends|unity one|flipkart|myntra|smart bazaar|ajio|nykaa)\b", "Shopping"),
    (r"\b(zomato|haldiram|droptheq|swiggy|burger king|bakington|bikanervala|mcdonald|belgian waffle|restaurant|cafe|pizza)\b", "Food"),
    (r"\b(airtel|jio|vi|bsnl|recharge|electricity|water|gas)\b", "Utilities"),
    (r"\b(pharmacy|apollo|medplus|hospital|clinic|bansal|doctor)\b", "Health"),
    (r"\b(rent|maintenance|society)\b", "Housing"),
    (r"\b(salary|refund|cashback|interest|edxsollp)\b", "Income"),
    (r"\b(vrinda|yavnika|mahima|esha|nitin|vivek|mohit|saket|shweta|dev|shashwat|arjun)\b", "Friends"),
    (r"\b(rani|parul)\b", "Family"),
]


def categorize(transaction: str) -> str:
    value = transaction or ""
    for pattern, category in CATEGORY_RULES:
        if re.search(pattern, value, re.IGNORECASE):
            return category
    return DEFAULT_CATEGORY

