from datetime import datetime, timedelta
from types import SimpleNamespace

from sqlalchemy import update

from bot.db import repo
from bot.db.models import Addition

CHAT = -100


def tg(uid, name="U"):
    return SimpleNamespace(id=uid, first_name=f"{name}{uid}", last_name=None, username=None)


async def test_counting_is_unique_and_ignores_self_join(session):
    assert await repo.record_addition(session, CHAT, 10, 100)
    assert await repo.record_addition(session, CHAT, 10, 101)
    # Bir a'zoni qayta qo'shish yoki boshqa odam qo'shishi hisoblanmaydi
    assert not await repo.record_addition(session, CHAT, 10, 100)
    assert not await repo.record_addition(session, CHAT, 20, 100)
    # O'zi kirgan (havola orqali) — hisoblanmaydi
    assert not await repo.record_addition(session, CHAT, 30, 30)
    assert await repo.record_addition(session, CHAT, 20, 200)

    rnd = await repo.current_round(session, CHAT)
    rows = await repo.rating(session, rnd.id, subtract_left=True)
    assert [(r.user_id, r.count, r.place) for r in rows] == [(10, 2, 1), (20, 1, 2)]


async def test_left_members_subtracted_and_restored(session):
    await repo.record_addition(session, CHAT, 10, 100)
    await repo.record_addition(session, CHAT, 10, 101)
    await repo.mark_left(session, CHAT, 100)
    rnd = await repo.current_round(session, CHAT)
    assert (await repo.rating(session, rnd.id, True))[0].count == 1
    assert (await repo.rating(session, rnd.id, False))[0].count == 2
    # Chiqib, qaytadan qo'shilsa — yana asl qo'shgan odamga hisoblanadi, ikki marta emas
    assert not await repo.record_addition(session, CHAT, 20, 100)
    rows = await repo.rating(session, rnd.id, True)
    assert [(r.user_id, r.count) for r in rows] == [(10, 2)]


async def test_tie_break_first_to_reach_wins(session):
    await repo.record_addition(session, CHAT, 20, 200)
    await repo.record_addition(session, CHAT, 10, 100)
    rnd = await repo.current_round(session, CHAT)
    assert [r.user_id for r in await repo.rating(session, rnd.id, True)] == [20, 10]


async def test_rounds_and_win_counts(session):
    await repo.upsert_user(session, tg(10))
    await repo.record_addition(session, CHAT, 10, 100)
    r1 = await repo.current_round(session, CHAT)
    assert await repo.add_win(session, r1.id, 10, 1, 1) == (1, True)
    # Bir turda ikki marta g'olib bo'lmaydi
    assert await repo.add_win(session, r1.id, 10, 1, 1) == (1, False)

    r2 = await repo.start_new_round(session, CHAT)
    assert r2.number == 2 and r2.id != r1.id
    assert await repo.rating(session, r2.id, True) == []  # reyting noldan
    await repo.record_addition(session, CHAT, 10, 101)
    assert await repo.add_win(session, r2.id, 10, 1, 1) == (2, True)

    rows = await repo.rating(session, r2.id, True)
    assert rows[0].wins == 2
    st = await repo.user_stats(session, CHAT, 10)
    assert (st.round_count, st.total_count, st.wins, st.place, st.won_this_round) == (1, 2, 2, 1, True)

    await repo.remove_win(session, r2.id, 10)
    assert await repo.win_count(session, 10) == 1


async def test_settings_defaults_and_toggle(session):
    assert await repo.get_flag(session, "delete_service")
    assert not await repo.toggle_flag(session, "delete_service")
    assert not await repo.get_flag(session, "delete_service")
    assert await repo.get_group_id(session, None) is None
    await repo.set_setting(session, "group_id", str(CHAT))
    assert await repo.get_group_id(session, None) == CHAT


async def set_times(session, member_id, added_at, left_at=None):
    await session.execute(update(Addition).where(Addition.member_id == member_id).values(added_at=added_at, left_at=left_at))
    await session.commit()


async def test_deadline_counts_only_until_deadline(session):
    """Muddatdan keyin qo'shilganlar hisoblanmaydi; muddatgacha chiqqanlar ayiriladi, keyin chiqqanlar qoladi."""
    deadline = datetime(2026, 11, 5, 18, 59, 59)
    for m in (100, 101, 102, 103):
        await repo.record_addition(session, CHAT, 10, m)
    await set_times(session, 100, deadline - timedelta(days=2))
    await set_times(session, 101, deadline - timedelta(days=2), left_at=deadline - timedelta(days=1))  # muddatgacha chiqdi
    await set_times(session, 102, deadline - timedelta(days=2), left_at=deadline + timedelta(hours=1))  # keyin chiqdi
    await set_times(session, 103, deadline + timedelta(minutes=1))  # muddatdan keyin qo'shildi

    rnd = await repo.current_round(session, CHAT)
    rows = await repo.rating(session, rnd.id, True, until=deadline)
    assert [(r.user_id, r.count, r.added, r.left) for r in rows] == [(10, 2, 3, 1)]
    assert (await repo.rating(session, rnd.id, False, until=deadline))[0].count == 3
    # Muddatsiz — barcha qo'shilganlar, chiqib ketgan ikkalasi ayiriladi
    assert [(r.count, r.added, r.left) for r in await repo.rating(session, rnd.id, True)] == [(2, 4, 2)]

    await repo.set_deadline(session, rnd, deadline)
    assert [r.count for r in await repo.round_rating(session, rnd)] == [2]


async def test_user_with_everyone_left_is_not_ranked(session):
    await repo.record_addition(session, CHAT, 10, 100)
    await repo.mark_left(session, CHAT, 100)
    rnd = await repo.current_round(session, CHAT)
    assert await repo.rating(session, rnd.id, True) == []
    assert [r.count for r in await repo.rating(session, rnd.id, False)] == [1]


def test_parse_deadline_uses_tashkent_time():
    assert repo.parse_deadline("05.11.2026") == datetime(2026, 11, 5, 18, 59, 59)
    assert repo.parse_deadline(" 05.11.2026  18:00 ") == datetime(2026, 11, 5, 13, 0)
    assert repo.parse_deadline("5/11/2026") == datetime(2026, 11, 5, 18, 59, 59)
    assert repo.parse_deadline("ertaga") is None
    assert repo.to_local(datetime(2026, 11, 5, 13, 0)) == datetime(2026, 11, 5, 18, 0)


async def test_winners_by_rule(session):
    for adder, members in ((10, range(100, 105)), (20, range(200, 203)), (30, range(300, 301))):
        for m in members:
            await repo.record_addition(session, CHAT, adder, m)
    rnd = await repo.current_round(session, CHAT)
    rows = await repo.round_rating(session, rnd)
    assert repo.winners_by_rule(rnd, rows) == []

    await repo.set_win_rule(session, rnd, "top", 2)
    assert [r.user_id for r in repo.winners_by_rule(rnd, rows)] == [10, 20]
    assert "TOP-2" in repo.rule_text(rnd)

    await repo.set_win_rule(session, rnd, "goal", 3)
    assert [r.user_id for r in repo.winners_by_rule(rnd, rows)] == [10, 20]
    await repo.set_win_rule(session, rnd, "goal", 100)
    assert repo.winners_by_rule(rnd, rows) == []

    await repo.set_win_rule(session, rnd, None, None)
    assert (rnd.win_mode, rnd.win_value) == (None, None)


async def test_templates_crud(session):
    t = await repo.add_template(session, "1-o'rin", "Tabriklaymiz {name}!")
    await repo.update_template(session, t.id, "Yangi {wins}")
    assert [x.text for x in await repo.list_templates(session)] == ["Yangi {wins}"]
    await repo.delete_template(session, t.id)
    assert await repo.list_templates(session) == []
