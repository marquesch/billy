from datetime import datetime


def formatted_date(date: str | datetime) -> str:
    if isinstance(date, datetime):
        return date.strftime("%Y-%m-%d")
    else:
        return date


def sql_today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def create_whatsapp_aligned_text(title: str, lines: dict) -> str:
    text = f"```{title}"

    longest = max([len(header) for header in lines.keys()])

    for header, value in lines.items():
        spaces = longest - len(header) + 1
        text += f"\n{header}{' ' * spaces}{value}"

    return text + "```"
