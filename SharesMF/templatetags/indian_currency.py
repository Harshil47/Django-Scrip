from django import template

register = template.Library()

@register.filter(name='indian_currency')
def indian_currency(value):
    try:
        # Convert to string to preserve full numeric value
        num_str = str(value)

        # Split the number into whole and decimal parts
        if '.' in num_str:
            whole, decimal = num_str.split('.')
        else:
            whole, decimal = num_str, None

        # Remove any existing commas from the whole part
        whole = whole.replace(',', '')

        # If number is less than or equal to 3 digits, no formatting needed
        if len(whole) <= 3:
            formatted = whole
        else:
            # Separate the last 3 digits
            last_three = whole[-3:]
            # Group the remaining digits in twos from right to left
            remaining = whole[:-3]
            groups = []
            while remaining:
                group = remaining[-2:] if len(remaining) >= 2 else remaining
                groups.insert(0, group)
                remaining = remaining[:-2]
            
            # Combine groups and last three digits
            formatted = ','.join(groups) + ',' + last_three

        # Add the decimal part back, if it exists
        if decimal:
            formatted = f"{formatted}.{decimal}"

        return formatted
    except (ValueError, TypeError):
        return value
