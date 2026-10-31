from types import SimpleNamespace

from bot.db import repo

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


async def test_templates_crud(session):
    t = await repo.add_template(session, "1-o'rin", "Tabriklaymiz {name}!")
    await repo.update_template(session, t.id, "Yangi {wins}")
    assert [x.text for x in await repo.list_templates(session)] == ["Yangi {wins}"]
    await repo.delete_template(session, t.id)
    assert await repo.list_templates(session) == []
