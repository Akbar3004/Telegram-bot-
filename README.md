# 🏆 Guruhga odam qo'shish konkursi boti

Bot guruhga kim nechta odam qo'shganini aniq hisoblaydi, "X Yni qo'shdi" xabarlarini o'chiradi
va adminga reyting, g'oliblarga mukofot xabarini yuborish hamda g'oliblar tarixini ko'rsatadi.

## Imkoniyatlar

**Guruhda**
- Kim kimni qo'shganini hisoblaydi. Har bir a'zo faqat **bir marta** hisoblanadi: chiqib qayta
  qo'shilish yoki boshqa odam qayta qo'shishi bilan hisobni ko'paytirib bo'lmaydi.
- Havola orqali o'zi kirganlar va botlar hisoblanmaydi.
- Guruhdan chiqib ketgan a'zolar hisobdan ayiriladi: 25 ta qo'shib, 15 tasi chiqib ketsa, reytingda
  **10 ta** ko'rinadi. Sozlamalarda o'chirilsa, 25 ta ko'rinadi.
- **Shaxsiy taklif havolasi:** har bir ishtirokchi botdan o'z havolasini oladi (`/link` yoki
  "🔗 Shaxsiy taklif havolam" tugmasi). Shu havola orqali kirgan har bir odam havola egasiga hisoblanadi.
  Bu maxfiylik sozlamasi tufayli guruhga to'g'ridan-to'g'ri qo'shib bo'lmaydigan odamlar uchun kerak.
- **`/top`** — guruhda hammaga TOP-10 reytingni ko'rsatadi. Bu buyruq daqiqada bir martadan ko'p
  ishlamaydi, eski `/top` xabari o'chiriladi. Ismlar havolasiz chiqadi, shuning uchun hech kimga
  bildirishnoma bormaydi. Xabar ostida "📊 Natijamni ko'rish" va "🔗 Shaxsiy havolamni olish" tugmalari bor.
- "Kim kimni qo'shdi" va "guruhdan chiqdi" degan xizmat xabarlarini o'chiradi.

**Admin panel** (botga `/start` bosilganda)
- Har safar **TOP-10 reyting** darhol ko'rinadi. To'liq reyting sahifalarga bo'lingan.
- Har bir foydalanuvchi yonida 🏆 belgisi: **necha marta g'olib bo'lgani**.
- **Profilga o'tish tugmalari:** reytingda har bir odam yonida 💬 tugmasi bor, kartada esa
  "💬 Profiliga o'tib yozish" tugmasi. Mukofot yuborilgandan keyingi hisobotda har bir g'olib uchun
  tugma chiqadi (avval xabar yetib bormaganlar). Agar foydalanuvchining maxfiylik sozlamasi tugmani
  taqiqlasa, xabar tugmasiz chiqadi va ism ustiga bosish orqali profil ochiladi.
- **Foydalanuvchi kartasi:** joriy va umumiy natija (shundan havola orqali nechta), o'rni,
  g'oliblik soni, kimlarni qo'shgani, bot orqali xabar yozish (matn, rasm, video va boshqalar).
- **Shablonlar:** mukofot xabarlarini oldindan yozib qo'yish. O'zgaruvchilar: `{name}`,
  `{mention}`, `{place}`, `{count}`, `{wins}`.
- **Mukofot yuborish:** shablon tanlanadi, ro'yxatdan ✅ bilan belgilanadi yoki TOP-1/3/5/10
  tugmasi bosiladi, ko'rinishi tekshiriladi va bir tugma bilan yuboriladi. Yetib bormagan xabarlar
  uchun profilga havolalar beriladi, ularga o'zingiz yozasiz.
- **Konkurs sharti** (🎯 tugmasi):
  - **Muddat**, masalan `05.11.2026` yoki `05.11.2026 18:00` (Toshkent vaqti). Shu vaqtgacha
    qo'shilganlar hisoblanadi. Muddatgacha guruhni tark etganlar ayiriladi, muddatdan keyin chiqqanlar
    hisobda qoladi.
  - **TOP-N** — muddatgacha eng ko'p qo'shgan N nafar g'olib bo'ladi, yoki **N ta qo'shish** —
    kamida N ta qo'shgan har bir ishtirokchi g'olib bo'ladi.
  - "👑 G'oliblar (shart)" — shartni bajarganlar ro'yxati. Mukofot oynasida "🎯 Shart bo'yicha
    g'oliblar" tugmasi ularni bir bosishda belgilaydi.
- **📢 Reytingni guruhga yuborish:** to'liq jadval (uzun bo'lsa, bir nechta xabarga bo'linadi). Har bir
  ishtirokchining hisobi, qo'shganlari va muddatgacha guruhni tark etganlar soni, konkurs sharti,
  shartni bajarganlar (🏆) va sonlar qanday hisoblangani tushuntiriladi.
- **Turlar:** "Yangi tur" bosilganda reyting noldan boshlanadi, tarix esa saqlanib qoladi.
- **G'oliblar tarixi:** har bir turda kim, nechanchi o'rin bilan va **nechanchi marta** g'olib bo'lgani.
- **Excel (CSV)** eksport.

**Admin tugmalari:** admin `/start` bosganda yozish maydoni ostida **🏆 Konkurs** (admin panel) va
**📈 Guruh statistikasi** tugmalari doim turadi.

**📈 Guruh statistikasi:** hozirgi a'zolar soni, kuzatuv boshlanganidan beri chiqib ketganlar soni,
joriy oy bilan o'tgan oyning taqqoslanishi (qo'shilganlar, chiqib ketganlar, sof o'sish, kunlik o'rtacha
qo'shilish va chiqish, oy boshidagi a'zolar soni). Statistika bot ulanganidan keyin yig'ila boshlaydi.
Post ko'rishlar sonini Telegram botlarga guruh xabarlari uchun bermaydi.

**👥 Ega va adminlar** (kod va Vercel'ga kirmasdan, botning o'zida):
- **Birinchi ega:** botga `https://t.me/<bot>?start=<WEBHOOK_SECRET>` havolasi orqali `/start` bosgan
  odam ega bo'ladi. Bu faqat ega hali belgilanmagan bo'lsa ishlaydi.
- **Adminlar:** admin panel → "👥 Adminlar va egalik" bo'limida ega yordamchi admin qo'shadi
  (kontakt tanlash, xabarini forward qilish yoki ID yozish orqali) yoki olib tashlaydi.
- **Egalikni topshirish** (botni sotish): bot bir martalik havola yaratadi. Uni bosgan odam ega bo'ladi,
  avvalgi ega esa adminlikdan chiqadi.
- `ADMIN_IDS` (Vercel) ixtiyoriy: undagilar har doim ega huquqiga ega. Botni sotsangiz, uni olib tashlang.

**Oddiy foydalanuvchi** `/start` bosganda pastda doim turadigan **"📊 Natijam"** va
**"🔗 Taklif havolam"** tugmalari chiqadi. Natijada hisobi, qo'shganlari va guruhni tark etganlar soni,
o'rni, g'oliblik soni, konkurs sharti va shartgacha nechta qolgani ko'rinadi.

> ⚠️ Telegram qoidasiga ko'ra bot faqat **botga /start bosgan** foydalanuvchiga xabar yubora oladi.
> Shuning uchun guruhda ishtirokchilarga botga start bosishni aytib qo'ying.

## 🚀 Vercel'ga joylashtirish (tavsiya etiladi)

Vercel'da bot **webhook** rejimida ishlaydi: Telegram har bir yangilanishni `https://<loyiha>.vercel.app/api/webhook`
manziliga yuboradi. Vercel fayllarni saqlamaydi, shuning uchun ma'lumotlar **PostgreSQL** bazasida turadi
(bepul Neon bazasi yetarli).

### 1. Kodni GitHub'dagi asosiy branchga o'tkazing
Vercel production'ni `main` branchdan oladi. Preview (boshqa branch) manzillari standart holda
**Vercel Authentication** bilan himoyalangan, Telegram ularga kira olmaydi. Shuning uchun kodni `main`ga
birlashtiring (yoki Vercel'da Settings → Deployment Protection'ni o'chiring).

### 2. Vercel'da loyiha yarating
[vercel.com](https://vercel.com) → **Add New… → Project** → shu GitHub repozitoriyasini tanlang → **Deploy**.
Framework tanlash shart emas: `vercel.json` va `api/index.py` hammasini o'zi sozlaydi.

### 3. Bazani ulang
Loyiha ichida **Storage → Create Database → Neon (Serverless Postgres)** → loyihaga ulang.
Neon loyihaga `DATABASE_URL` o'zgaruvchisini avtomatik qo'shadi. Agar u boshqa nom bilan qo'shilgan bo'lsa
(masalan `POSTGRES_URL`), uning qiymatini `DATABASE_URL` nomi bilan qo'shing. `postgres://...?sslmode=require`
ko'rinishidagi havolani shundayligicha qo'yavering, bot uni o'zi moslaydi.

Supabase yoki boshqa PostgreSQL ham ishlaydi.

### 4. Environment Variables
**Settings → Environment Variables** bo'limiga quyidagilarni qo'shing:

| Nomi | Qiymati |
|---|---|
| `BOT_TOKEN` | BotFather bergan token |
| `ADMIN_IDS` | (ixtiyoriy) Super-adminlar ID'si, vergul bilan: `111111111,222222222`. Ega va adminlarni botning o'zida ham belgilash mumkin |
| `WEBHOOK_SECRET` | 16+ belgili tasodifiy kalit (A-Z, a-z, 0-9, `_`, `-`) |
| `DATABASE_URL` | 3-qadamdagi baza havolasi |
| `GROUP_ID` | (ixtiyoriy) guruh ID'si, bo'sh qoldirsangiz guruhda `/bind` yozasiz |

`WEBHOOK_SECRET` yaratish:
```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

O'zgaruvchilarni qo'shgandan keyin **Deployments → ⋯ → Redeploy** bosing.

### 5. Webhookni yoqing (bir marta)
Brauzerda oching:
```
https://<loyiha>.vercel.app/api/setup?secret=<WEBHOOK_SECRET>
```
Javobda `"ok": true` va `"webhook": "https://<loyiha>.vercel.app/api/webhook"` chiqsa, bot ishga tushdi ✅

### 6. Guruhni ulang
Botni guruhga qo'shing va admin qiling (**xabarlarni o'chirish** va **foydalanuvchilarni taklif qilish** huquqlari bilan),
guruhda `/bind` yozing va botga shaxsiy chatda `/start` bosing.

### Eslatmalar
- Bot javob bermasa, avval Vercel'da **Logs** bo'limini, keyin `/api/setup` sahifasini oching.
  U yerdagi `pending_updates` qiymati Telegram yuborolmay turgan yangilanishlar sonini ko'rsatadi.
- Botni kompyuterda `python -m bot` bilan ishga tushirsangiz, webhook o'chadi (polling rejimi).
  Vercel'ga qaytish uchun `/api/setup` sahifasini yana oching.
- `/api/setup` havolasida maxfiy kalit bor, uni hech kimga bermang.

## Server yoki Docker'da ishga tushirish (polling)

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
5. Botni guruhga qo'shing va **admin** qiling. Kerakli huquqlar: **xabarlarni o'chirish** va
   **foydalanuvchilarni taklif qilish** (shaxsiy havolalar uchun).
   Admin bo'lmasa, Telegram botga a'zolar haqidagi yangilanishlarni yubormaydi.
6. Guruhda `/bind` deb yozing (yoki botni admin o'zi qo'shsa, guruh avtomatik ulanadi).
7. Botga shaxsiy chatda `/start` bosing va admin panel ochiladi.

## Testlar

```bash
pip install -r requirements-dev.txt
pytest
```

PostgreSQL'da ham sinash uchun:
```bash
TEST_POSTGRES_URL=postgresql://user:pass@localhost:5432/test_db pytest
```

## Tuzilishi

```
bot/
  __main__.py          — polling rejimida ishga tushirish (server/Docker)
  webhook.py           — Vercel uchun webhook ilova (ASGI)
  app.py               — Bot va Dispatcher yaratish
  db/fsm_storage.py    — dialog holatlarini bazada saqlash
  config.py            — .env sozlamalari
  db/models.py         — jadvallar (users, rounds, additions, wins, templates, settings)
  db/repo.py           — hisoblash va reyting mantig'i
  handlers/group.py    — guruh hodisalari (qo'shish, chiqish, xabarlarni o'chirish)
  handlers/user.py     — oddiy foydalanuvchi uchun /start
  handlers/admin/      — admin panel: menu, shablonlar, mukofot yuborish
api/index.py           — Vercel kirish nuqtasi
vercel.json            — Vercel sozlamalari
tests/                 — unit, to'liq oqim va webhook testlari
```
