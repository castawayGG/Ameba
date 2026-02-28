import re
import random


def spin(text: str) -> str:
    """Parse {option1|option2|option3} and pick one randomly. Supports nested spintax."""
    while '{' in text:
        # Find the innermost {...} group
        match = re.search(r'\{([^{}]+)\}', text)
        if not match:
            break
        options = match.group(1).split('|')
        chosen = random.choice(options)
        text = text[:match.start()] + chosen + text[match.end():]
    return text


def spin_with_variables(text: str, variables: dict) -> str:
    """First replace {{var}} placeholders, then spin."""
    if variables:
        for key, value in variables.items():
            text = text.replace('{{' + key + '}}', str(value))
    return spin(text)


def generate_previews(text: str, count: int = 5) -> list:
    """Generate N unique preview variants of the spintax text."""
    results = set()
    attempts = 0
    max_attempts = count * 10
    while len(results) < count and attempts < max_attempts:
        results.add(spin(text))
        attempts += 1
    return list(results)[:count]


def calculate_uniqueness(text: str) -> int:
    """Count the total number of possible unique variants.

    Processes the text iteratively (innermost groups first) to correctly
    handle nested spintax like {A|{B|C}}.
    """
    # Repeatedly resolve innermost non-nested groups until none remain
    work = text
    total = 1
    while '{' in work:
        match = re.search(r'\{([^{}]+)\}', work)
        if not match:
            break
        options = match.group(1).split('|')
        total *= len(options)
        # Replace the matched group with a placeholder so we keep processing
        work = work[:match.start()] + '__PLACEHOLDER__' + work[match.end():]
    return total
