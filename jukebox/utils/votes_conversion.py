"""
Votes conversion logic with bonuses.

Handles conversion from Coins (global currency) to Votes (party-specific).
Applies volume-based bonuses to incentivize bulk purchases.
"""
from typing import Tuple


def calculate_votes_from_coins(coins: int) -> int:
    """
    Calculates votes obtained from a quantity of coins with bonuses.

    Bonus tiers:
    - 20+ Coins → 3.0x (20 Coins = 60 Votes, +20 bonus)
    - 10-19 Coins → 2.5x (10 Coins = 25 Votes, +5 bonus)
    - 5-9 Coins → 2.2x (5 Coins = 11 Votes, +1 bonus)
    - 3-4 Coins → 2.0x (3 Coins = 6 Votes)
    - 1-2 Coins → 2.0x (1 Coin = 2 Votes)

    Args:
        coins: Quantity of coins to convert

    Returns:
        Number of votes obtained

    Example:
        >>> calculate_votes_from_coins(1)
        2
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
    elif coins >= 3:
        return int(coins * 2.0)
    else:
        return coins * 2


def convert_coins_to_votes(user, party, coins_to_convert: int) -> Tuple[bool, str, int]:
    """
    Converts Coins to Votes with validation and database registration.

    Creates a VotePackage record to track the conversion and deducts
    the coins from the user's global credits.

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

    # Validation
    if coins_to_convert <= 0:
        return False, "La quantitat ha de ser superior a 0", 0

    if coins_to_convert > user.credits:
        return False, f"No tens prous Coins (tens {user.credits})", 0

    # Calculate votes with bonuses
    votes_to_add = calculate_votes_from_coins(coins_to_convert)

    # Create conversion record
    VotePackage.objects.create(
        user=user,
        party=party,
        votes_purchased=votes_to_add
    )

    # Deduct coins
    user.credits -= coins_to_convert
    user.save(update_fields=['credits'])

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
    bonus_active = coins >= 3

    return {
        'votes': votes,
        'multiplier': round(multiplier, 1),
        'bonus_active': bonus_active
    }
