import re
from django.utils.text import slugify


CYRILLIC_TO_LATIN = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch", "ъ": "",
    "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}


def transliterate(value: str) -> str:
    result = []
    for char in str(value):
        lower_char = char.lower()
        transliterated = CYRILLIC_TO_LATIN.get(lower_char, char)

        if char.isupper() and transliterated:
            transliterated = transliterated.capitalize()

        result.append(transliterated)

    return "".join(result)


def cyrillic_slugify(value: str) -> str:
    prepared_value = transliterate(value)
    slug = slugify(prepared_value, allow_unicode=False)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug
