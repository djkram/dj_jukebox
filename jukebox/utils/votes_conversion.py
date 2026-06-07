"""
Votes conversion logic with bonuses.

Handles conversion from Coins (global currency) to Votes (party-specific).
Applies volume-based bonuses to incentivize bulk purchases.
"""
from typing import Tuple
from django.db import transaction


def calculate_votes_from_coins(coins: int) -> int:
    """
    Calculates votes obtained from a quantity of coins with bonuses.

    Bonus tiers:
    - 20+ Coins → 3.0x (20 Coins = 60 Votes)
    - 10-19 Coins → 2.5x (10 Coins = 25 Votes)
    - 5-9 Coins → 2.2x (5 Coins = 11 Votes)
    - 1-4 Coins → 2.0x (1 Coin = 2 Votes)

    Args:
        coins: Quantity of coins to convert

    Returns:
        Number of votes obtained

    Example:
        >>> calculate_votes_from_coins(5)
        11
        >>> calculate_votes_from_coins(10)
        25
        >>> calculate_votes_from_coins(20)
        60
    """
    if coins >= 20:
        return int(coins * 3.0)
    elif coins >= 10:
        return int(coins * 2.5)
    elif coins >= 5:
        return int(coins * 2.2)
    else:
        return int(coins * 2.0)


def convert_coins_to_votes(user, party, coins_to_convert: int) -> Tuple[bool, str, int]:
    """
    Converts Coins to Votes with validation and database registration.

    Creates a VotePackage record to track the conversion and deducts
    the coins from party free coins first, then global user credits.

    Args:
        user: User instance
        party: Party instance
        coins_to_convert: Quantity of coins to convert

    Returns:
        Tuple[success: bool, error_msg: str, votes_obtained: int]
        - success: True if conversion successful
        - error_msg: Error message if failed, empty string if successful
        - votes_obtained: Number of votes obtained (0 if failed)

    Example:
        success, error, votes = convert_coins_to_votes(user, party, 10)
        if success:
            print(f"Obtained {votes} votes!")
        else:
            print(f"Error: {error}")
    """
    from jukebox.models import VotePackage
    from jukebox.votes import spend_user_coins_for_party

    # Validation
    if coins_to_convert < 5:
        return False, "El mínim per convertir és 5 Coins", 0

    # Calculate votes with bonuses
    votes_to_add = calculate_votes_from_coins(coins_to_convert)

    with transaction.atomic():
        spent = spend_user_coins_for_party(
            user,
            party,
            coins_to_convert,
            reason='coins_converted_to_votes',
        )
        if not spent:
            return False, f"No tens prous Coins", 0

        VotePackage.objects.create(
            user=user,
            party=party,
            votes_purchased=votes_to_add
        )

    user.refresh_from_db(fields=['credits'])
    return True, "", votes_to_add


def get_conversion_preview(coins: int) -> dict:
    """
    Gets conversion preview without executing it.

    Useful for displaying conversion rates in UI before user confirms.

    Args:
        coins: Quantity of coins

    Returns:
        Dict with info:
        - votes: Number of votes that would be obtained
        - multiplier: Effective multiplier (e.g., 2.5)
        - bonus_active: Whether bonus tier is active (coins >= 3)

    Example:
        >>> preview = get_conversion_preview(10)
        >>> print(f"{preview['votes']} votes at {preview['multiplier']}x")
        25 votes at 2.5x
    """
    votes = calculate_votes_from_coins(coins)
    multiplier = votes / coins if coins > 0 else 0
    bonus_active = coins >= 10

    return {
        'votes': votes,
        'multiplier': round(multiplier, 1),
        'bonus_active': bonus_active
    }
