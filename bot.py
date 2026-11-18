"""AI front desk for a business in Telegram: answers clients, collects a booking, sends it to the owner.
Run: python bot.py    Chat in the terminal (no Telegram): python bot.py --chat    Offline check: python bot.py --selftest
Settings: .env (keys) and business.json (business data).
"""
import csv, json, re, sys, time, urllib.error, urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent
MAX_INPUT = 1000   # long client messages are cut
MAX_HISTORY = 16   # how many recent messages the bot remembers


def load_env():
    env = {}
    path = ROOT / ".env"
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                key, value = line.split("=", 1)
                env[key.strip()] = value.strip()
    return env


def post_json(url, payload, headers=None, timeout=60):
    req = urllib.request.Request(url, json.dumps(payload).encode("utf-8"),
                                 {"Content-Type": "application/json", "User-Agent": "demo-bot/1.0", **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def system_prompt(biz, now):
    services = "\n".join(f"- {s['name']}: {s['price']}" for s in biz["services"])
    return f"""You are the front desk of {biz['name']} ({biz['kind']}). You answer clients in a messenger.
Now: {now:%A, %B %d, %Y, %I:%M %p}. Address: {biz['address']}. Hours: {biz['hours']}.
Services and prices:
{services}
Also: {biz.get('extra', '')}

Rules:
- Reply briefly and naturally, 1-3 sentences, in the client's language.
- Answer only questions about this business. Take prices and services only from the list above, never invent anything.
- Do not diagnose and do not promise results. If something is not in the data, say the office manager will follow up.
- If the client wants to book, ask one by one for: name, service, preferred day and time, phone number.
- Once all four are known, confirm the booking to the client and add this service line as the last line:
BOOKING|name|service|exact date and time, e.g. Thu, Nov 19, 3:00 PM|phone
- Booking times must fall within the opening hours; otherwise offer the nearest open time.
- Add the service line once, and only after the client has given all four items."""


def extract_booking(reply):
    """Splits the BOOKING|... service line off the client-facing text."""
    booking = None
    lines = []
    for line in reply.splitlines():
        m = re.match(r"\s*BOOKING\|(.+?)\|(.+?)\|(.+?)\|(.+)", line)
        if m:
            booking = [part.strip() for part in m.groups()]
        else:
            lines.append(line)
    return "\n".join(lines).strip(), booking


class Bot:
    def __init__(self, env, biz):
        self.biz = biz
        self.tg = f"https://api.telegram.org/bot{env.get('TELEGRAM_TOKEN')}/"
        self.llm_url = env.get("LLM_BASE_URL", "https://api.groq.com/openai/v1").rstrip("/") + "/chat/completions"
        self.llm_key = env["LLM_API_KEY"]
        self.model = env.get("LLM_MODEL", "openai/gpt-oss-120b")
        self.owner = env.get("OWNER_CHAT_ID")
        self.history = {}

    def send(self, chat_id, text):
        post_json(self.tg + "sendMessage", {"chat_id": chat_id, "text": text})

    def ask_llm(self, chat_id):
        messages = [{"role": "system", "content": system_prompt(self.biz, datetime.now())}] + self.history[chat_id]
        data = post_json(self.llm_url, {"model": self.model, "messages": messages, "temperature": 0.3, "max_tokens": 500},
                         {"Authorization": f"Bearer {self.llm_key}"})
        return data["choices"][0]["message"]["content"]

    def save_booking(self, booking, user):
        path = ROOT / "bookings.csv"
        new = not path.exists()
        with path.open("a", newline="", encoding="utf-8-sig") as f:  # utf-8-sig so Excel opens it cleanly
            w = csv.writer(f)
            if new:
                w.writerow(["received", "name", "service", "time", "phone", "telegram"])
            w.writerow([f"{datetime.now():%Y-%m-%d %H:%M}", *booking, user])
        if self.owner:
            name, service, when, phone = booking
            self.send(self.owner, f"New booking\nName: {name}\nService: {service}\nWhen: {when}\nPhone: {phone}\nTelegram: {user}")

    def handle(self, msg):
        chat = msg["chat"]
        text = (msg.get("text") or "").strip()
        if chat.get("type") != "private" or not text:
            return
        chat_id = chat["id"]
        if text == "/start":
            self.history[chat_id] = []
            return self.send(chat_id, self.biz["greeting"])
        if text == "/id":
            return self.send(chat_id, f"Your chat id: {chat_id}")
        user = "@" + msg["from"]["username"] if msg["from"].get("username") else str(chat_id)
        self.send(chat_id, self.reply(chat_id, text, user))

    def reply(self, chat_id, text, user):
        hist = self.history.setdefault(chat_id, [])
        hist.append({"role": "user", "content": text[:MAX_INPUT]})
        del hist[:-MAX_HISTORY]
        try:
            answer = self.ask_llm(chat_id)
        except (urllib.error.URLError, KeyError, TimeoutError, ValueError) as e:
            print("LLM error:", e, getattr(e, "read", lambda: b"")()[:300])
            return "One moment, I'm checking with the office manager. Please write again in a minute."
        hist.append({"role": "assistant", "content": answer})
        visible, booking = extract_booking(answer)
        if booking:
            self.save_booking(booking, user)
        return visible or "Booked, thank you!"

    def chat(self):
        """Talk to the bot in the terminal: same prompt and booking logic, no Telegram."""
        print(self.biz["greeting"])
        while (text := input("> ").strip()) not in ("", "exit"):
            print(self.reply("terminal", text, "terminal"))

    def run(self):
        offset = 0
        print("Bot running:", self.biz["name"])
        while True:
            try:
                updates = post_json(self.tg + "getUpdates", {"offset": offset, "timeout": 25, "allowed_updates": ["message"]}, timeout=40)
            except (urllib.error.URLError, TimeoutError, ValueError) as e:
                print("Telegram error:", e)
                time.sleep(5)
                continue
            for u in updates.get("result", []):
                offset = u["update_id"] + 1
                if "message" in u:
                    try:
                        self.handle(u["message"])
                    except Exception as e:  # one bad update must not stop the bot
                        print("handle error:", repr(e))


def selftest():
    biz = json.loads((ROOT / "business.json").read_text(encoding="utf-8"))
    prompt = system_prompt(biz, datetime(2026, 11, 14, 22, 0))
    assert biz["services"][0]["name"] in prompt and "November 14, 2026" in prompt
    text, b = extract_booking("You're booked, Emily!\nBOOKING|Emily|Teeth cleaning|Thursday 3:00 PM|(512) 555-0110")
    assert text == "You're booked, Emily!" and b == ["Emily", "Teeth cleaning", "Thursday 3:00 PM", "(512) 555-0110"], (text, b)
    assert extract_booking("A cleaning is $120.") == ("A cleaning is $120.", None)
    print("selftest ok")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    env = load_env()
    chat = "--chat" in sys.argv
    missing = [k for k in ("LLM_API_KEY",) + (() if chat else ("TELEGRAM_TOKEN",)) if not env.get(k)]
    if missing:
        sys.exit("Missing in .env: " + ", ".join(missing))
    bot = Bot(env, json.loads((ROOT / "business.json").read_text(encoding="utf-8")))
    bot.chat() if chat else bot.run()
