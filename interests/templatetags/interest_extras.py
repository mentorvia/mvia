from django import template
register = template.Library()

@register.filter
def times(value, arg):
    """Multiply: used for tree indentation. {{ depth|times:1.5 }}"""
    try:
        return float(value) * float(arg)
    except (ValueError, TypeError):
        return 0
