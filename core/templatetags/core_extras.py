from django import template

register = template.Library()


@register.filter
def get(dictionary, key):
    """Get item from dictionary in template"""
    return dictionary.get(key) if dictionary else None
