from django.db.models import Q


NEGATIVE_VOTE_TYPES = ("dislike", "skip")
VALID_VOTE_TYPES = ("like", "dislike")


def normalize_vote_type(vote_type):
    if vote_type == "skip":
        return "dislike"
    return vote_type


def negative_vote_q(field_name="vote__vote_type"):
    return Q(**{f"{field_name}__in": NEGATIVE_VOTE_TYPES})
