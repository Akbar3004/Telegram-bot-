"""Gemini orqali kiyim rasmidan chiroyli mahsulot rasmi yaratish (REST API, aiohttp)."""
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
