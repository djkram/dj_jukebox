from .models import Vote, VotePackage
from django.db.models import Sum

def get_user_votes_left(user, party):
    base_votes = party.max_votes_per_user
    extra_votes = VotePackage.objects.filter(user=user, party=party).aggregate(
        total=Sum('votes_purchased')
    )['total'] or 0
    total_votes_allowed = base_votes + extra_votes

    votes_used = Vote.objects.filter(user=user, party=party).count()
    return max(0, total_votes_allowed - votes_used)
