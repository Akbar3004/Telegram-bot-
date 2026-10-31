"""Kiyim rasmidan chiroyli mahsulot rasmi yaratish: ChatGPT (OpenAI) yoki Gemini, REST API orqali (aiohttp)."""
import base64
import logging

import aiohttp

log = logging.getLogger(__name__)

API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
TIMEOUT = 50  # soniya: Vercel funksiyasi 60 soniyada to'xtatiladi

# Kiyimning o'zi o'zgarmasligi — sotuvda eng muhimi
KEEP_GARMENT = (
    "Keep the garment EXACTLY as in the photo: the same color and shade, fabric texture, pattern, print, "
    "logos, buttons, zippers, stitching, cut, length and proportions. Do not add, remove or redesign any detail. "
    "Do not add any text, letters, watermark or price tags. Photorealistic, high quality, sharp focus."
)

# kalit: (tugma matni, AI uchun topshiriq)
STYLES: dict[str, tuple[str, str]] = {
    "studio": ("📸 Studiya fon", "Create a professional e-commerce product photo of this garment on a clean, "
                                "seamless light studio background with soft, even lighting and a subtle shadow."),
    "mannequin": ("🧍 Maneken", "Show this garment worn by an invisible (ghost) mannequin so it has a natural 3D "
                               "shape, on a clean light studio background, professional catalog lighting."),
    "model": ("👗 Model kiygan", "Show a fashion model wearing this garment in a modern fashion photoshoot, "
                                "neutral studio background, flattering soft light, the garment clearly visible."),
    "flatlay": ("🌿 Chiroyli muhit", "Create a stylish flat lay photo of this garment neatly arranged on an elegant "
                                    "surface with a few tasteful minimal props, soft natural daylight, top-down view."),
}


class AiImageError(Exception):
    """Foydalanuvchiga ko'rsatiladigan tushunarli xato."""


def build_prompt(style: str) -> str:
    return f"{STYLES[style][1]} {KEEP_GARMENT}"


async def post_json(url: str, body: dict, api_key: str) -> dict:
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=TIMEOUT)) as http:
        async with http.post(url, json=body, headers={"x-goog-api-key": api_key}) as resp:
            return await resp.json(content_type=None)


async def generate(api_key: str, model: str, photo: bytes, style: str, mime: str = "image/jpeg") -> bytes:
    """Kiyim rasmini va uslubni Gemini'ga yuboradi, yangi rasmni (bayt) qaytaradi."""
    body = {
        "contents": [{"parts": [
            {"text": build_prompt(style)},
            {"inline_data": {"mime_type": mime, "data": base64.b64encode(photo).decode()}},
        ]}],
        "generationConfig": {"responseModalities": ["IMAGE"]},
    }
    try:
        data = await post_json(API_URL.format(model=model), body, api_key)
    except TimeoutError as e:
        raise AiImageError("AI javob berishga ulgurmadi. Qaytadan urinib ko'ring.") from e
    except aiohttp.ClientError as e:
        raise AiImageError(f"AI xizmatiga ulanib bo'lmadi: {e}") from e

    if "error" in data:
        err = data["error"]
        log.warning("Gemini xatosi: %s", err)
        code = err.get("code")
        if code in (401, 403):
            raise AiImageError("Gemini API kaliti noto'g'ri yoki bu model uchun ruxsat yo'q.")
        if code == 402:
            raise AiImageError("Gemini loyihasida oldindan to'langan balans tugagan. AI Studio → Projects → Billing "
                               "bo'limida balansni to'ldiring (ai.studio/projects).")
        if code == 429 and "free_tier" in str(err.get("message", "")):
            raise AiImageError("API kalit bepul (Free Tier) loyihaga tegishli — rasm modeli uchun bepul limit yo'q. "
                               "Google AI Studio'da shu loyihaga billing (Cloud kreditlari) ulang.")
        if code == 429:
            raise AiImageError("Limit tugagan (yoki billing ulanmagan). Keyinroq urinib ko'ring yoki "
                               "Google Cloud'da kredit/billingni tekshiring.")
        raise AiImageError(f"Gemini xatosi: {err.get('message', 'noma`lum')[:300]}")

    for cand in data.get("candidates", []):
        for part in (cand.get("content") or {}).get("parts", []):
            inline = part.get("inline_data") or part.get("inlineData")
            if inline and inline.get("data"):
                return base64.b64decode(inline["data"])
    reason = next((c.get("finishReason") for c in data.get("candidates", []) if c.get("finishReason")), None)
    block = (data.get("promptFeedback") or {}).get("blockReason")
    log.warning("Gemini rasm qaytarmadi: finish=%s block=%s", reason, block)
    raise AiImageError("AI rasm qaytarmadi" + (f" ({block or reason})" if block or reason else "") +
                       ". Boshqa rasm yoki uslub bilan urinib ko'ring.")


# --- OpenAI (ChatGPT) ---------------------------------------------------------

OPENAI_URL = "https://api.openai.com/v1/images/edits"
OPENAI_TIMEOUT = 55  # OpenAI sekinroq; Vercel funksiyasi 60 soniyada to'xtatiladi


async def post_openai(form: aiohttp.FormData, api_key: str) -> dict:
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=OPENAI_TIMEOUT)) as http:
        async with http.post(OPENAI_URL, data=form, headers={"Authorization": f"Bearer {api_key}"}) as resp:
            return await resp.json(content_type=None)


async def openai_generate(api_key: str, model: str, photo: bytes, style: str, mime: str = "image/jpeg") -> bytes:
    """Kiyim rasmini OpenAI images/edits API'siga yuboradi, yangi rasmni (bayt) qaytaradi."""
    ext = "png" if mime == "image/png" else "webp" if mime == "image/webp" else "jpg"
    form = aiohttp.FormData()
    form.add_field("model", model)
    form.add_field("prompt", build_prompt(style))
    form.add_field("image", photo, filename=f"garment.{ext}", content_type=mime)
    form.add_field("size", "1024x1536")  # tik (portret) rasm — Telegram va Instagram uchun qulay
    form.add_field("quality", "medium")  # "high" juda sekin — Vercel vaqt chegarasiga sig'maydi
    form.add_field("n", "1")
    try:
        data = await post_openai(form, api_key)
    except TimeoutError as e:
        raise AiImageError("ChatGPT javob berishga ulgurmadi. Qaytadan urinib ko'ring.") from e
    except aiohttp.ClientError as e:
        raise AiImageError(f"OpenAI'ga ulanib bo'lmadi: {e}") from e

    if data.get("error"):
        err = data["error"]
        log.warning("OpenAI xatosi: %s", err)
        code, msg = err.get("code") or err.get("type"), str(err.get("message", ""))
        if code in ("invalid_api_key",) or "Incorrect API key" in msg:
            raise AiImageError("OpenAI API kaliti noto'g'ri.")
        if code in ("insufficient_quota", "billing_hard_limit_reached"):
            raise AiImageError("OpenAI hisobida balans tugagan. platform.openai.com → Billing bo'limida balansni to'ldiring.")
        if "verif" in msg.lower():
            raise AiImageError("OpenAI bu rasm modeli uchun tashkilotni tasdiqlashni so'rayapti: platform.openai.com → "
                               "Settings → Organization → Verify. Tasdiqlangach 15-30 daqiqada ishlaydi.")
        if code == "moderation_blocked" or "safety" in msg.lower():
            raise AiImageError("OpenAI bu rasmni xavfsizlik qoidasi bo'yicha rad etdi. Boshqa rasm bilan urinib ko'ring.")
        if code == "rate_limit_exceeded":
            raise AiImageError("OpenAI limiti: bir daqiqadan so'ng qayta urinib ko'ring.")
        raise AiImageError(f"OpenAI xatosi: {msg[:300] or code}")

    for item in data.get("data") or []:
        if item.get("b64_json"):
            return base64.b64decode(item["b64_json"])
    log.warning("OpenAI rasm qaytarmadi: %s", str(data)[:500])
    raise AiImageError("ChatGPT rasm qaytarmadi. Qaytadan urinib ko'ring.")


PROVIDERS = {"gemini": "Gemini", "openai": "ChatGPT"}


def pick_provider(settings) -> str | None:
    """Qaysi xizmat ishlatiladi: AI_PROVIDER sozlamasi, bo'lmasa kaliti bor xizmat (ChatGPT ustun)."""
    keys = {"openai": settings.openai_api_key, "gemini": settings.gemini_api_key}
    if settings.ai_provider in keys and keys[settings.ai_provider]:
        return settings.ai_provider
    return next((p for p in ("openai", "gemini") if keys[p]), None)


async def generate_with(settings, photo: bytes, style: str, mime: str = "image/jpeg") -> bytes:
    provider = pick_provider(settings)
    if provider == "openai":
        model = settings.openai_image_model or "gpt-image-2"
        return await openai_generate(settings.openai_api_key, model, photo, style, mime)
    if provider == "gemini":
        model = settings.gemini_image_model or "gemini-2.5-flash-image"
        return await generate(settings.gemini_api_key, model, photo, style, mime)
    raise AiImageError("AI kaliti sozlanmagan.")
