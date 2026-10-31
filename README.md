# 🏆 Guruhga odam qo'shish konkursi boti

Bot guruhga kim nechta odam qo'shganini aniq hisoblaydi, "X Yni qo'shdi" xabarlarini o'chiradi
va adminga reyting, g'oliblarga mukofot xabarini yuborish hamda g'oliblar tarixini ko'rsatadi.

## Imkoniyatlar

**Guruhda**
- Kim kimni qo'shganini hisoblaydi. Har bir a'zo faqat **bir marta** hisoblanadi: chiqib qayta
  qo'shilish yoki boshqa odam qayta qo'shishi bilan hisobni ko'paytirib bo'lmaydi.
- Havola orqali o'zi kirganlar va botlar hisoblanmaydi.
- Guruhdan chiqib ketgan a'zolar hisobdan ayiriladi (sozlamalarda o'chirib qo'ysa bo'ladi).
- "Kim kimni qo'shdi" va "guruhdan chiqdi" degan xizmat xabarlarini o'chiradi.

**Admin panel** (botga `/start` bosilganda)
- Har safar **TOP-10 reyting** darhol ko'rinadi. To'liq reyting sahifalarga bo'lingan.
- Har bir foydalanuvchi yonida 🏆 belgisi: **necha marta g'olib bo'lgani**.
- **Foydalanuvchi kartasi:** joriy va umumiy natija, o'rni, g'oliblik soni, kimlarni qo'shgani,
  profilga havola, bot orqali xabar yozish (matn, rasm, video va boshqalar).
- **Shablonlar:** mukofot xabarlarini oldindan yozib qo'yish. O'zgaruvchilar: `{name}`,
  `{mention}`, `{place}`, `{count}`, `{wins}`.
- **Mukofot yuborish:** shablon tanlanadi, ro'yxatdan ✅ bilan belgilanadi yoki TOP-1/3/5/10
  tugmasi bosiladi, ko'rinishi tekshiriladi va bir tugma bilan yuboriladi. Yetib bormagan xabarlar
  uchun profilga havolalar beriladi, ularga o'zingiz yozasiz.
- **Turlar:** "Yangi tur" bosilganda reyting noldan boshlanadi, tarix esa saqlanib qoladi.
- **G'oliblar tarixi:** har bir turda kim, nechanchi o'rin bilan va **nechanchi marta** g'olib bo'lgani.
- **Excel (CSV)** eksport.

**Oddiy foydalanuvchi** `/start` bosganda o'z natijasini, o'rnini va g'oliblik sonini ko'radi.

> ⚠️ Telegram qoidasiga ko'ra bot faqat **botga /start bosgan** foydalanuvchiga xabar yubora oladi.
> Shuning uchun guruhda ishtirokchilarga botga start bosishni aytib qo'ying.

## O'rnatish

1. [@BotFather](https://t.me/BotFather) orqali bot yarating va token oling.
2. BotFather'dagi **Group Privacy** sozlamasini o'zgartirish shart emas: xizmat xabarlari baribir keladi.
3. `.env.example` faylidan nusxa olib, `.env` nomi bilan saqlang va to'ldiring:
   ```bash
   cp .env.example .env
   ```
4. Ishga tushiring (Python 3.11+):
   ```bash
   pip install -r requirements.txt
   python -m bot
   ```
   Yoki Docker orqali:
   ```bash
   docker compose up -d --build
   ```
5. Botni guruhga qo'shing va **admin** qiling. Kamida **xabarlarni o'chirish** huquqi kerak.
   Admin bo'lmasa, Telegram botga a'zolar haqidagi yangilanishlarni yubormaydi.
6. Guruhda `/bind` deb yozing (yoki botni admin o'zi qo'shsa, guruh avtomatik ulanadi).
7. Botga shaxsiy chatda `/start` bosing va admin panel ochiladi.

## Testlar

```bash
pip install -r requirements-dev.txt
pytest
```

## Tuzilishi

```
bot/
  __main__.py          — ishga tushirish
  config.py            — .env sozlamalari
  db/models.py         — jadvallar (users, rounds, additions, wins, templates, settings)
  db/repo.py           — hisoblash va reyting mantig'i
  handlers/group.py    — guruh hodisalari (qo'shish, chiqish, xabarlarni o'chirish)
  handlers/user.py     — oddiy foydalanuvchi uchun /start
  handlers/admin/      — admin panel: menu, shablonlar, mukofot yuborish
tests/                 — unit va to'liq oqim testlari
```
