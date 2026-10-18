"""Formatowanie danych do wyświetlenia w dokumentach."""


def bank_account(number: str) -> str:
    """Numer rachunku w grupach cyfr, np. "PL83 1050 1012 1000 0090 3127 8782".

    Numery w innym formacie są zwracane bez zmian.
    """
    country, digits = (number[:2], number[2:]) if number[:2].isalpha() else ("", number)
    if len(digits) == 26 and digits.isdigit():
        groups = " ".join(digits[i : i + 4] for i in range(2, 26, 4))
        return f"{country}{digits[:2]} {groups}"
    return number
