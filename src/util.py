from datetime import datetime


def formatted_date(date):
    if isinstance(date, datetime):
        return date.strftime("%Y-%m-%d")
    else:
        return date


def sql_today():
    return datetime.now().strftime("%Y-%m-%d")
