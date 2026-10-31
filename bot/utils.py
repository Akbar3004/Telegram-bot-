import html

from .db.models import User


def full_name(user: User | None, user_id: int | None = None) -> str:
    if user is None:
        return f"ID {user_id}" if user_id else "Noma'lum"
    name = " ".join(p for p in (user.first_name, user.last_name) if p).strip()
    return name or (f"@{user.username}" if user.username else f"ID {user.id}")


def mention(user: User | None, user_id: int) -> str:
    """Bosilganda profilni ochadigan HTML havola."""
    return f'<a href="tg://user?id={user_id}">{html.escape(full_name(user, user_id))}</a>'


MEDALS = {1: "🥇", 2: "🥈", 3: "🥉"}


def place_icon(place: int) -> str:
    return MEDALS.get(place, f"{place}.")


def render_template(text: str, *, user: User | None, user_id: int, place: int | None, count: int, wins: int) -> str:
    """Shablondagi o'zgaruvchilarni almashtiradi: {name} {mention} {place} {count} {wins}."""
    values = {
        "{name}": html.escape(full_name(user, user_id)),
        "{mention}": mention(user, user_id),
        "{place}": str(place) if place else "—",
        "{count}": str(count),
        "{wins}": str(wins),
    }
    for k, v in values.items():
        text = text.replace(k, v)
    return text


PLACEHOLDERS_HELP = (
    "Shablonda quyidagi o'zgaruvchilardan foydalanishingiz mumkin:\n"
    "<code>{name}</code> — foydalanuvchi ismi\n"
    "<code>{mention}</code> — profilga havola bilan ism\n"
    "<code>{place}</code> — reytingdagi o'rni\n"
    "<code>{count}</code> — qo'shgan odamlari soni\n"
    "<code>{wins}</code> — nechanchi marta g'olib bo'layotgani\n\n"
    "Matnni Telegram'ning o'zida formatlashingiz mumkin (qalin, kursiv, havola va h.k.) — formatlash saqlanadi."
)
