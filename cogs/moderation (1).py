import discord
from discord.ext import commands
from datetime import datetime, timedelta
from collections import defaultdict
import unicodedata
import re
from rapidfuzz import fuzz
import config
from .appeals import AppealButton, appeal_logs, user_role_backup

from PIL import Image, ImageDraw, ImageFont
import io

# ──────────────────────────────────────────────────────────────────────────────
#  SLUR LIST  (canonical forms only — detection handles all variants)
# ──────────────────────────────────────────────────────────────────────────────
TARGET_SLURS = [
    # Racial
    "nigger", "nigga", "coon", "spook", "sambo", "jigaboo", "porchmonkey",
    "darkie", "pickaninny", "wetback", "beaner", "spic", "chink", "gook",
    "slope", "zipperhead", "towelhead", "sandnigger", "raghead", "cameljockey",
    "kike", "hymie", "jewboy", "cracker", "honky", "whitey", "redskin",
    "injun", "halfbreed",
    # Homophobic / transphobic
    "faggot", "fag", "dyke", "tranny", "shemale", "ladyboy", "battyboy",
    "poof", "poofter", "homo", "sodomite", "pillowbiter",
    # Ableist
    "retard", "retarded", "spastic", "mong",
]

user_timeout_counts = {}

# ──────────────────────────────────────────────────────────────────────────────
#  HOMOGLYPH / SUBSTITUTION MAP
#  Covers: leet speak, unicode lookalikes, cyrillic, greek, fullwidth, symbols,
#  superscript/subscript, enclosed letters, mathematical variants, braille hints
# ──────────────────────────────────────────────────────────────────────────────
SUBSTITUTION_MAP = {
    # ── numbers → letters ────────────────────────────────────────────────────
    "0": "o", "1": "i", "2": "z", "3": "e", "4": "a",
    "5": "s", "6": "g", "7": "t", "8": "b", "9": "g",
    # ── symbols → letters ────────────────────────────────────────────────────
    "!": "i", "@": "a", "$": "s", "+": "t", "|": "i",
    "¡": "i", "£": "e", "€": "e", "¥": "y", "¢": "c",
    "®": "r", "©": "c", "°": "o", "×": "x", "÷": "o",
    "¿": "i", "~": "", "^": "", "\"": "", "'": "",
    "`": "", ".": "", ",": "", "-": "", "_": "",
    "*": "", "/": "", "\\": "", " ": "", "(": "c",
    "\\/": "v",
    # ── cyrillic lookalikes → latin ───────────────────────────────────────────
    "а": "a", "е": "e", "і": "i", "о": "o", "р": "p",
    "с": "c", "у": "y", "х": "x", "ё": "e", "ӓ": "a",
    "в": "b", "м": "m", "н": "n", "к": "k", "т": "t",
    "з": "e", "ч": "ch", "ш": "w", "щ": "w", "ю": "io",
    "я": "ya", "г": "g", "д": "d", "ж": "zh", "л": "l",
    "п": "p", "ф": "f", "ц": "ts", "э": "e", "ъ": "",
    "ь": "", "ы": "i",
    # ── greek → latin ────────────────────────────────────────────────────────
    "α": "a", "β": "b", "γ": "g", "δ": "d", "ε": "e",
    "ζ": "z", "η": "n", "θ": "0", "ι": "i", "κ": "k",
    "λ": "l", "μ": "m", "ν": "n", "ξ": "x", "ο": "o",
    "π": "p", "ρ": "r", "σ": "s", "τ": "t", "υ": "u",
    "φ": "f", "χ": "x", "ψ": "ps", "ω": "o",
    # ── fullwidth latin ───────────────────────────────────────────────────────
    "ａ": "a", "ｂ": "b", "ｃ": "c", "ｄ": "d", "ｅ": "e",
    "ｆ": "f", "ｇ": "g", "ｈ": "h", "ｉ": "i", "ｊ": "j",
    "ｋ": "k", "ｌ": "l", "ｍ": "m", "ｎ": "n", "ｏ": "o",
    "ｐ": "p", "ｑ": "q", "ｒ": "r", "ｓ": "s", "ｔ": "t",
    "ｕ": "u", "ｖ": "v", "ｗ": "w", "ｘ": "x", "ｙ": "y",
    "ｚ": "z",
    # ── superscript digits/letters ────────────────────────────────────────────
    "⁰": "0", "¹": "1", "²": "2", "³": "3", "⁴": "4",
    "⁵": "5", "⁶": "6", "⁷": "7", "⁸": "8", "⁹": "9",
    "ⁿ": "n", "ⁱ": "i",
    # ── subscript digits ──────────────────────────────────────────────────────
    "₀": "0", "₁": "1", "₂": "2", "₃": "3", "₄": "4",
    "₅": "5", "₆": "6", "₇": "7", "₈": "8", "₉": "9",
    # ── enclosed/circled letters (Ⓐ–Ⓩ, ①–⑳) ──────────────────────────────
    **{chr(0x24B6 + i): chr(ord('a') + i) for i in range(26)},   # Ⓐ–Ⓩ
    **{chr(0x24D0 + i): chr(ord('a') + i) for i in range(26)},   # ⓐ–ⓩ
    # ── mathematical bold/italic/script/fraktur variants ─────────────────────
    # Bold a–z: 𝐚–𝐳  (U+1D41A–U+1D433)
    **{chr(0x1D41A + i): chr(ord('a') + i) for i in range(26)},
    # Bold A–Z: 𝐀–𝐙  (U+1D400–U+1D419)
    **{chr(0x1D400 + i): chr(ord('a') + i) for i in range(26)},
    # Italic a–z: 𝑎–𝑧  (U+1D44E–U+1D467)
    **{chr(0x1D44E + i): chr(ord('a') + i) for i in range(26)},
    # Italic A–Z: 𝐴–𝑍  (U+1D434–U+1D44D)
    **{chr(0x1D434 + i): chr(ord('a') + i) for i in range(26)},
    # Script a–z: 𝒶–𝓏  (U+1D4B6–U+1D4CF)
    **{chr(0x1D4B6 + i): chr(ord('a') + i) for i in range(26)},
    # Fraktur a–z: 𝔞–𝔷  (U+1D51E–U+1D537 approximate)
    **{chr(0x1D51E + i): chr(ord('a') + i) for i in range(26)},
    # Sans-serif a–z: 𝗮–𝘇  (U+1D5EE–U+1D607)
    **{chr(0x1D5EE + i): chr(ord('a') + i) for i in range(26)},
    # Monospace a–z: 𝚊–𝚣  (U+1D68A–U+1D6A3)
    **{chr(0x1D68A + i): chr(ord('a') + i) for i in range(26)},
    # ── regional indicator letters (🇦–🇿 flag emoji letters) ─────────────────
    **{chr(0x1F1E6 + i): chr(ord('a') + i) for i in range(26)},
    # ── Latin Extended / accented variants ────────────────────────────────────
    "à": "a", "á": "a", "â": "a", "ã": "a", "ä": "a", "å": "a", "æ": "ae",
    "ç": "c", "è": "e", "é": "e", "ê": "e", "ë": "e",
    "ì": "i", "í": "i", "î": "i", "ï": "i",
    "ð": "d", "ñ": "n",
    "ò": "o", "ó": "o", "ô": "o", "õ": "o", "ö": "o", "ø": "o",
    "ù": "u", "ú": "u", "û": "u", "ü": "u",
    "ý": "y", "þ": "th", "ÿ": "y",
}

# ── Characters that are purely invisible / zero-width → strip them ────────────
INVISIBLE_RE = re.compile(
    r"[\u200b\u200c\u200d\u200e\u200f\u2060\u2061\u2062\u2063"
    r"\u2064\uFEFF\u00AD\u034F\u061C\u115F\u1160\u17B4\u17B5"
    r"\u180E\u3164\uFFA0\u00A0\u2000-\u200A\u202F\u205F\u3000]"
)

# ── Emoji letter pattern: 🅰 🅱 etc (negative-squared latin) ──────────────────
EMOJI_LETTER_MAP = {
    "🅰": "a", "🅱": "b", "🆎": "ae", "🆑": "cl", "🆒": "cool",
    "🆓": "free", "🆔": "id", "🆕": "new", "🆖": "ng", "🆗": "ok",
    "🆘": "sos", "🆙": "up", "🆚": "vs",
}

# ── Morse-like single char emoji that people use as letters ──────────────────
EMOJI_SUBSTITUTE_MAP = {
    "🅽": "n", "🅸": "i", "🅶": "g", "🅴": "e", "🆁": "r",
    "🅲": "c", "🅾": "o", "🅵": "f", "🅰": "a", "🅱": "b",
}


class Moderation(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        self.spam  = defaultdict(list)
        self.pings = defaultdict(list)

    # ──────────────────────────────────────────────────────────────────────────
    #  TIMEOUT ESCALATION
    # ──────────────────────────────────────────────────────────────────────────
    def get_timeout_duration(self, user_id):
        count = user_timeout_counts.get(user_id, 0) + 1
        user_timeout_counts[user_id] = count
        if count <= 2:
            return timedelta(days=1)
        if count <= 4:
            return timedelta(days=3)
        return timedelta(days=7)

    # ──────────────────────────────────────────────────────────────────────────
    #  PIPELINE STEP 1 — Swap out emoji letter blocks before anything else
    # ──────────────────────────────────────────────────────────────────────────
    def _replace_emoji_letters(self, text: str) -> str:
        for emoji, letter in {**EMOJI_LETTER_MAP, **EMOJI_SUBSTITUTE_MAP}.items():
            text = text.replace(emoji, letter)
        return text

    # ──────────────────────────────────────────────────────────────────────────
    #  PIPELINE STEP 2 — Strip invisible / zero-width characters
    # ──────────────────────────────────────────────────────────────────────────
    def _strip_invisible(self, text: str) -> str:
        return INVISIBLE_RE.sub("", text)

    # ──────────────────────────────────────────────────────────────────────────
    #  PIPELINE STEP 3 — Unicode NFKD normalise + drop diacritics (zalgo etc.)
    # ──────────────────────────────────────────────────────────────────────────
    def _unicode_normalise(self, text: str) -> str:
        text = unicodedata.normalize("NFKD", text)
        text = "".join(c for c in text if unicodedata.category(c) != "Mn")
        return text

    # ──────────────────────────────────────────────────────────────────────────
    #  PIPELINE STEP 4 — Apply substitution map (longest-match first)
    # ──────────────────────────────────────────────────────────────────────────
    def _apply_substitutions(self, text: str) -> str:
        result = []
        i = 0
        while i < len(text):
            # Try longest matches first (up to 4 chars for things like "\/")
            matched = False
            for length in (4, 3, 2):
                chunk = text[i:i+length]
                if chunk in SUBSTITUTION_MAP:
                    result.append(SUBSTITUTION_MAP[chunk])
                    i += length
                    matched = True
                    break
            if not matched:
                ch = text[i].lower()
                result.append(SUBSTITUTION_MAP.get(ch, ch))
                i += 1
        return "".join(result)

    # ──────────────────────────────────────────────────────────────────────────
    #  PIPELINE STEP 5 — Collapse repeated characters  (niiigger → nigger)
    #  Keep max 2 so "fagg" still matches "fag" via fuzzy
    # ──────────────────────────────────────────────────────────────────────────
    def _collapse_repeats(self, text: str) -> str:
        return re.sub(r"(.)\1{2,}", r"\1\1", text)

    # ──────────────────────────────────────────────────────────────────────────
    #  FULL NORMALISE PIPELINE
    # ──────────────────────────────────────────────────────────────────────────
    def normalize(self, text: str) -> str:
        text = self._replace_emoji_letters(text)
        text = self._strip_invisible(text)
        text = self._unicode_normalise(text)
        text = text.lower()
        text = self._apply_substitutions(text)
        text = self._collapse_repeats(text)
        text = re.sub(r"[^a-z0-9]", "", text)
        return text

    # ──────────────────────────────────────────────────────────────────────────
    #  SPACED TOKEN EXTRACTOR  — catches "n.i.g.g.e.r", "n i g g e r" etc.
    # ──────────────────────────────────────────────────────────────────────────
    def _extract_spaced_tokens(self, original: str):
        pattern = re.compile(r"(?:[a-z0-9][^a-z0-9]{1,3}){2,}[a-z0-9]", re.IGNORECASE)
        tokens = []
        for match in pattern.finditer(original.lower()):
            collapsed = re.sub(r"[^a-z0-9]", "", match.group())
            tokens.append(collapsed)
        return tokens

    # ──────────────────────────────────────────────────────────────────────────
    #  GENERATE DEDUPED CANDIDATE STRINGS
    #  Produces multiple cleaned views of the message for maximum coverage
    # ──────────────────────────────────────────────────────────────────────────
    def _candidates(self, text: str) -> list[str]:
        candidates = set()

        # 1. Full pipeline on original
        candidates.add(self.normalize(text))

        # 2. All spaces stripped first, then pipeline
        nospace = re.sub(r"\s+", "", text)
        candidates.add(self.normalize(nospace))

        # 3. Pipeline on each word individually
        for word in re.findall(r"\S+", text):
            candidates.add(self.normalize(word))

        # 4. Spaced/separated tokens (n-i-g-g-e-r)
        for token in self._extract_spaced_tokens(text):
            candidates.add(self.normalize(token))

        # 5. Remove ALL non-alpha first, then pipeline (catches heavy punctuation padding)
        stripped = re.sub(r"[^a-zA-Z0-9]", "", text)
        candidates.add(self.normalize(stripped))

        return [c for c in candidates if c]

    # ──────────────────────────────────────────────────────────────────────────
    #  MAIN SLUR DETECTION
    # ──────────────────────────────────────────────────────────────────────────
    def detect_slurs(self, text: str) -> list:
        found = set()

        for slur in TARGET_SLURS:
            norm_slur = self.normalize(slur)
            slur_len  = len(norm_slur)

            for candidate in self._candidates(text):
                if not candidate:
                    continue

                # ── Direct substring ──────────────────────────────────────────
                if norm_slur in candidate:
                    found.add(slur)
                    break

                # ── Whole-string fuzzy (short messages / single words) ────────
                if len(candidate) <= slur_len + 5:
                    if fuzz.ratio(candidate, norm_slur) >= 80:
                        found.add(slur)
                        break

                # ── Sliding window fuzzy ──────────────────────────────────────
                #  Window = slur length ±2 to catch insertions & deletions
                hit = False
                for win in (slur_len, slur_len + 1, slur_len + 2, slur_len - 1):
                    if win < 2:
                        continue
                    for i in range(len(candidate) - win + 1):
                        chunk = candidate[i:i + win]
                        if fuzz.ratio(chunk, norm_slur) >= 83:
                            found.add(slur)
                            hit = True
                            break
                    if hit:
                        break

                if slur in found:
                    break

        return list(found)

    # ──────────────────────────────────────────────────────────────────────────
    #  WAGER DETECTION
    # ──────────────────────────────────────────────────────────────────────────
    def detect_wager(self, text: str) -> bool:
        norm = self.normalize(text)

        # Direct hit anywhere in message
        if "wager" in norm:
            return True

        # Whole-string fuzzy (for very short messages)
        if fuzz.ratio(norm, "wager") >= 88:
            return True

        # Sliding window — catches padded/split variants
        norm_wager = "wager"
        win = len(norm_wager)
        for i in range(max(0, len(norm) - win + 1)):
            chunk = norm[i:i + win + 1]
            if fuzz.ratio(chunk, norm_wager) >= 88:
                return True

        # Per-word check
        for word in re.findall(r"\S+", text):
            if fuzz.ratio(self.normalize(word), "wager") >= 88:
                return True

        return False

    # ──────────────────────────────────────────────────────────────────────────
    #  EVIDENCE IMAGE
    # ──────────────────────────────────────────────────────────────────────────
    def create_evidence_image(self, messages):
        width  = 800
        height = 40 + (len(messages) * 40)
        img  = Image.new("RGB", (width, height), (54, 57, 63))
        draw = ImageDraw.Draw(img)
        font = ImageFont.load_default()
        y = 10
        for msg in messages:
            text = f"{msg.author}: {msg.content}"
            draw.text((10, y), text, fill=(255, 255, 255), font=font)
            y += 35
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)
        return buffer

    # ──────────────────────────────────────────────────────────────────────────
    #  MESSAGE PROCESSOR
    # ──────────────────────────────────────────────────────────────────────────
    async def process_message(self, message):

        if message.author.bot:
            return

        # ── WAGER CHECK ───────────────────────────────────────────────────────
        if self.detect_wager(message.content):
            try:
                await message.delete()
            except discord.NotFound:
                pass

            embed = discord.Embed(
                title="❌ Incorrect Term",
                description=(
                    f"{message.author.mention}\n\n"
                    "**`wager` → `tokens`**\n\n"
                    "This is **not** a wagers site — it is purely a **tokens** site.\n"
                    "Please use the correct terminology."
                ),
                color=discord.Color.orange()
            )
            embed.set_footer(text="This message was automatically deleted.")

            await message.channel.send(embed=embed, delete_after=12)
            return

        # ── SLUR CHECK ────────────────────────────────────────────────────────
        slurs = self.detect_slurs(message.content)

        if not slurs:
            return

        # Collect last 10 messages from this user for evidence
        history = []
        async for msg in message.channel.history(limit=100):
            if msg.author == message.author:
                history.append(msg)
            if len(history) >= 10:
                break
        history.reverse()

        log_text = "\n".join(f"{m.author}: {m.content}" for m in history)
        appeal_logs[message.author.id] = log_text
        image_buffer = self.create_evidence_image(history)

        try:
            await message.delete()
        except discord.NotFound:
            pass

        member   = message.author
        duration = self.get_timeout_duration(member.id)

        # Back up the user's roles before timeout
        roles_to_backup = [
            r.id for r in member.roles
            if r != member.guild.default_role and not r.managed
        ]
        user_role_backup[member.id] = roles_to_backup

        await member.timeout(duration, reason=f"Slur detected: {', '.join(slurs)}")

        # DM the user
        dm_embed = discord.Embed(
            title="🚫 Severe Language Detected",
            description=(
                "Use of slurs is **not** permitted.\n\n"
                "**Note:** If your appeal is denied your timeout counter will "
                "restart to the initial timeout."
            ),
            color=discord.Color.red()
        )
        try:
            await member.send(embed=dm_embed, view=AppealButton(member))
        except Exception:
            pass

        # ── LOG TO STAFF CHANNEL with role pings ──────────────────────────────
        log_channel = self.bot.get_channel(config.LOG_CHANNEL)
        if log_channel:
            # Build the staff ping string from config
            staff_pings = " ".join(f"<@&{r}>" for r in config.STAFF_ROLES)

            evidence = discord.Embed(
                title="🔨 Moderation Action — Slur Detected",
                color=discord.Color.orange(),
                timestamp=datetime.utcnow()
            )
            evidence.add_field(name="User",     value=f"{member.mention} (`{member.id}`)", inline=True)
            evidence.add_field(name="Channel",  value=message.channel.mention,             inline=True)
            evidence.add_field(name="Duration", value=str(duration),                       inline=True)
            evidence.add_field(name="Slur(s)",  value=", ".join(f"`{s}`" for s in slurs), inline=False)
            evidence.set_image(url="attachment://evidence.png")

            file = discord.File(image_buffer, filename="evidence.png")

            # Send pings as plain content so they actually notify, embed as separate
            await log_channel.send(content=staff_pings, embed=evidence, file=file)

    # ──────────────────────────────────────────────────────────────────────────
    #  LISTENERS
    # ──────────────────────────────────────────────────────────────────────────
    @commands.Cog.listener()
    async def on_message(self, message):
        await self.process_message(message)
        await self.bot.process_commands(message)

    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
        if before.content == after.content:
            return
        await self.process_message(after)


async def setup(bot):
    await bot.add_cog(Moderation(bot))
