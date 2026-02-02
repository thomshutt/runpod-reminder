# runpod-reminder
Telegram bot for reminding me when I've left a Runpod pod running too long.

## What it does
- Runs on a 30-minute GitHub Actions schedule.
- Checks for Runpod pods running longer than 2 hours.
- Sends a Telegram alert with pod details.
- Allows terminating a pod by replying with `/terminate <pod_id>`.

## Setup
### 1) Create a Telegram bot
1. Open Telegram and chat with `@BotFather`.
2. Use `/newbot`, then copy the bot token it provides.

### 2) Get your Telegram chat ID
1. Start a chat with your bot (send any message).
2. Visit:
   - `https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates`
3. Find the `chat.id` field in the response. That is your `TELEGRAM_CHAT_ID`.

### 3) Add GitHub repository secrets
Add these secrets to your repo:
- `RUNPOD_API_KEY`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

### 4) Enable the workflow
The workflow is defined at `.github/workflows/runpod-reminder.yml` and runs every 30 minutes.

## Configuration
These environment variables are supported (set in the workflow):
- `MAX_AGE_HOURS` (default `2`)
- `ALERT_INTERVAL_MINUTES` (default `30`, prevents repeated alerts for the same pod)

## Terminating a pod
Reply in Telegram with:
```
/terminate <pod_id>
```

## References
- Runpod list pods API: https://docs.runpod.io/api-reference/pods/GET/pods
- Runpod delete pod API: https://docs.runpod.io/api-reference/pods/DELETE/pods/podId
