from .models import Party

def selected_party(request):
    party_id = request.session.get('selected_party_id')
    party = None
    if party_id:
        try:
            party = Party.objects.get(id=party_id)
        except Party.DoesNotExist:
            party = None
    return {'selected_party': party}
