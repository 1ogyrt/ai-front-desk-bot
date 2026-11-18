# AI front desk bot for a dental clinic (Telegram)

A Telegram bot that works as the clinic's front desk 24/7: answers questions about services, prices, hours and insurance, then books an appointment and sends it to the owner.

**Demo business:** Brightside Dental, a family clinic in Austin, TX (fictional).

## What it does
- Answers in plain language, only from the clinic's own data (`business.json`). No made-up prices.
- Never diagnoses: medical questions are redirected to an exam.
- Books step by step: name → service → date and time → phone. Respects opening hours (no Sunday bookings).
- Each booking is sent to the owner in Telegram and saved to `bookings.csv` (opens in Excel / Google Sheets).

## Example dialog
```
Client: Hi, how much is a teeth cleaning?
Bot:    A teeth cleaning is $120. Let us know if you'd like to schedule an appointment!
Client: Do you take Delta Dental?
Bot:    Yes, we accept Delta Dental PPO plans.
Client: Can you fix my tooth pain, is it a cavity?
Bot:    We can't diagnose over chat, but we recommend a new-patient exam with X-rays...
Client: I want to book a cleaning on Sunday
Bot:    We're closed on Sundays, but we can schedule your cleaning on Monday...
...
Owner gets: New booking — Mike Rodriguez, Teeth cleaning, Sat, Nov 21, 10:00 AM, (512) 555-0199
```

## Stack
Python 3 (standard library only, no dependencies), Telegram Bot API, any OpenAI-compatible LLM API (default: Groq, `openai/gpt-oss-120b`).

## Run
1. Create a bot with [@BotFather](https://t.me/BotFather) and get a free key at [console.groq.com](https://console.groq.com).
2. Create `.env`:
   ```
   TELEGRAM_TOKEN=...
   LLM_API_KEY=...
   OWNER_CHAT_ID=...   # send /id to the bot to get it
   ```
3. `python bot.py`

Try it without Telegram: `python bot.py --chat`. Offline self-check: `python bot.py --selftest`.

## Adapt to another business
Edit `business.json` (name, hours, services, prices, notes). The same bot works for a salon, auto shop, gym or any appointment-based business.
