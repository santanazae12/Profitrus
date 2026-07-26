# CarFlip AI Telegram Bot

## What already works

- User location by city/state/ZIP
- AI vehicle listing analysis
- Seller negotiation scripts
- Buyer reply scripts
- Repair diagnosis guidance
- Parts compatibility guidance and store links
- Manually saved deal feed
- Profit calculations
- Market Pulse database and CSV importer
- Railway/Replit-ready health server
- SQLite user and deal storage

## Important Marketplace limitation

The project does not secretly scrape Facebook accounts. Connect an approved Meta
Marketplace/Content Library source, a licensed automotive data provider, or a compliant
user-authorized connector inside `providers/marketplace.py`.

## Easiest setup: Replit

1. Create a new **Python Repl**.
2. Upload every file and folder from this ZIP.
3. Open **Secrets** and add:
   - `TELEGRAM_BOT_TOKEN`
   - `OPENAI_API_KEY`
   - `OPENAI_MODEL` = `gpt-4.1-mini`
4. Press **Run**.
5. Open your Telegram bot and send `/start`.
6. Use Replit Deployments if you want it online continuously.

## Railway setup

1. Upload this project to a GitHub repository or deploy with Railway CLI.
2. Create a Railway service from the repository.
3. Add Variables:
   - `TELEGRAM_BOT_TOKEN`
   - `OPENAI_API_KEY`
   - `OPENAI_MODEL` = `gpt-4.1-mini`
4. Deploy. Railway uses `python main.py`.

## Load sample Market Pulse data

Rename `market_stats.example.csv` to `market_stats.csv`, then run:

```bash
python scripts/import_market_data.py
```

## Bot commands

- `/start`
- `/menu`
- `/location`
- `/analyze`
- `/deals`
- `/market`
- `/repair`
- `/parts`
- `/seller`
- `/buyer`
- `/adddeal`

## Next production upgrades

- Approved Marketplace/data-provider connector
- VIN/history provider
- Valuation provider
- Parts inventory/pricing APIs
- Geocoding and nearby-state calculations
- Stripe subscriptions
- Admin dashboard
- Scheduled deal alerts
