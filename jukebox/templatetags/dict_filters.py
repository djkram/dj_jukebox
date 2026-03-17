from django import template

register = template.Library()

@register.filter
def get_item(dictionary, key):
    """
    Obté un valor d'un diccionari usant una clau.
    Ús: {{ my_dict|get_item:my_key }}
    """
    if dictionary is None:
        return None
    return dictionary.get(key)
