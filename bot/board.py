"""Guruhga yuboriladigan reyting matnlari: /top va to'liq jadval. Ismlar havolasiz — hech kim bezovta qilinmaydi."""
import html

from .db import repo
from .db.models import Round
from .utils import full_name, place_icon

MAX_LEN = 3800  # Telegram xabari 4096 belgidan oshmasin


def explain_text(subtract_left: bool) -> str:
    """Jadvaldagi sonlar nimani bildirishini tushuntiradi."""
    if subtract_left:
        how = ("Hisob = qo'shgan odamlari <b>minus</b> ulardan muddatgacha guruhni tark etganlar. "
               "Masalan: 25 ta qo'shib, 15 tasi chiqib ketsa — hisob 10 ta.")
    else:
        how = "Hisob = qo'shgan odamlari (guruhdan chiqib ketganlar ham hisoblanadi)."
    return (
        f"ℹ️ <i>{how}\n"
        "Har bir a'zo faqat bir marta hisoblanadi. Havola orqali o'zi kirganlar va botlar hisoblanmaydi.</i>"
    )


def row_line(r: repo.RatingRow, winner_ids: set[int] | frozenset = frozenset()) -> str:
    mark = " 🏆" if r.user_id in winner_ids else ""
    line = f"{place_icon(r.place)} {html.escape(full_name(r.user, r.user_id))} — <b>{r.count}</b> ta{mark}"
    if r.left:
        line += f" <i>({r.added} qo'shgan, {r.left} chiqib ketgan)</i>"
    return line


def header(rnd: Round, title: str) -> list[str]:
    lines = [f"{title} (tur #{rnd.number})"]
    rule = repo.rule_text(rnd)
    if rule:
        lines += ["", rule]
    return lines + [""]


def full_board(rnd: Round, rows: list[repo.RatingRow], subtract_left: bool) -> list[str]:
    """To'liq reyting jadvali, kerak bo'lsa bir nechta xabarga bo'lingan."""
    winners = repo.winners_by_rule(rnd, rows)
    ids = {r.user_id for r in winners}
    total_added = sum(r.added for r in rows)
    total_left = sum(r.left for r in rows)
    intro = header(rnd, "📋 <b>To'liq reyting jadvali</b>") + [
        f"👥 Ishtirokchilar: <b>{len(rows)}</b> | Qo'shilganlar: <b>{total_added}</b>"
        + (f" | Muddatgacha chiqib ketganlar: <b>{total_left}</b>" if total_left else ""),
        "",
    ]
    if not rows:
        intro.append("<i>Hozircha hech kim odam qo'shmagan.</i>")
    body = [row_line(r, ids) for r in rows]
    outro = [""]
    if rnd.win_mode:
        outro.append(f"🏆 — shart bo'yicha g'olib ({len(winners)} nafar)" if winners else "🏆 Hozircha shartni bajargan ishtirokchi yo'q")
    outro.append(explain_text(subtract_left))

    messages, cur = [], "\n".join(intro)
    for line in body + outro:
        if len(cur) + len(line) + 1 > MAX_LEN:
            messages.append(cur)
            cur = line
        else:
            cur = f"{cur}\n{line}" if cur else line
    messages.append(cur)
    return messages
