from django import template

register = template.Library()


@register.filter
def dur(seconds):
    """93 -> 1m 33s."""
    try:
        s = int(seconds or 0)
    except (TypeError, ValueError):
        return ""
    if s < 60:
        return f"{s}s"
    if s < 3600:
        return f"{s // 60}m {s % 60:02d}s"
    return f"{s // 3600}h {s % 3600 // 60:02d}m"


@register.filter
def total(rows, key):
    return sum((r.get(key) or 0) if isinstance(r, dict) else (getattr(r, key, 0) or 0) for r in rows)


@register.filter
def flag(code):
    if not code or len(code) != 2 or not code.isalpha():
        return ""
    return "".join(chr(0x1F1E6 + ord(c) - 65) for c in code.upper())


@register.simple_tag
def svederlytics_script():
    """{% load sl_tags %}{% svederlytics_script %} in the base template, before </body>."""
    from django.templatetags.static import static
    from django.utils.html import format_html
    return format_html('<script src="{}" defer></script>', static("svederlytics/sl.js"))
