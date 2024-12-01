from django import template

register = template.Library()

@register.filter(name='indian_currency')
def indian_currency(value):
    try:
        # Convert to string to preserve full numeric value
        num_str = str(value)

        # Remove any existing commas
        num_str = num_str.replace(',', '')

        # If number is less than or equal to 3 digits, return as is
        if len(num_str) <= 3:
            return num_str

        # Start from the right side
        # First, separate the last 3 digits
        last_three = num_str[-3:]
        
        # Get the remaining digits
        remaining = num_str[:-3]
        
        # Group the remaining digits in twos from right to left
        groups = []
        while remaining:
            # Take last two digits (or whatever is left)
            group = remaining[-2:] if len(remaining) >= 2 else remaining
            groups.insert(0, group)
            remaining = remaining[:-2]
        
        # Combine the groups
        result = ','.join(groups) + ',' + last_three

        return result
    except (ValueError, TypeError):
        return value