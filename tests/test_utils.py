from bot.db.models import User
from bot.utils import render_template


def test_render_template_escapes_and_fills():
    u = User(id=5, first_name="<Ali>", last_name=None, username=None)
    out = render_template("{name} {mention} {place} {count} {wins}", user=u, user_id=5, place=2, count=17, wins=3)
    assert out == '&lt;Ali&gt; <a href="tg://user?id=5">&lt;Ali&gt;</a> 2 17 3'
