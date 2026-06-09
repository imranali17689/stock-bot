# Stock Signal Engine

An automated stock sentiment analysis system that analyzes news for a watchlist of stocks using Finnhub API and Claude AI, then stores results in Supabase.

## Features

- 📊 Analyzes 10 major tech stocks: AAPL, NVDA, MSFT, GOOGL, AMZN, META, TSLA, JPM, V, AMD
- 📰 Fetches last 7 days of company news from Finnhub API
- 🧠 Uses Claude Haiku 4.5 for cost-effective sentiment analysis
- 💾 Automatically saves results to Supabase database
- ⏰ Runs daily at 8:00 AM Eastern time via APScheduler
- 📝 Comprehensive logging to both console and file

## Setup

1. **Install Dependencies:**
   ```bash
   source venv/bin/activate
   pip install -r requirements.txt
   ```

2. **Configure Environment:**
   - Copy `.env` and fill in your API keys:
     - `FINNHUB_API_KEY`: Get from [Finnhub](https://finnhub.io/)
     - `ANTHROPIC_API_KEY`: Get from [Anthropic](https://console.anthropic.com/)
     - `SUPABASE_URL` & `SUPABASE_SECRET_KEY`: From your Supabase project

3. **Database Setup:**
   Create a `signals` table in Supabase with these columns:
   ```sql
   CREATE TABLE signals (
     id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
     ticker TEXT NOT NULL,
     sentiment_score INTEGER NOT NULL,
     direction TEXT NOT NULL,
     confidence TEXT NOT NULL,
     summary TEXT NOT NULL,
     article_count INTEGER NOT NULL,
     created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
   );
   ```

## Usage

### Run Signal Engine Once
```bash
python signal_engine.py
```

### Run Scheduler (Daily at 8 AM ET)
```bash
python scheduler.py
```

### Test Scheduler Immediately
```bash
python scheduler.py --run-now
```

## Files

- `signal_engine.py` - Core sentiment analysis engine
- `scheduler.py` - Daily scheduler using APScheduler  
- `.env` - Environment variables (not in git)
- `.gitignore` - Git ignore rules
- `requirements.txt` - Python dependencies
- `scheduler.log` - Scheduler logs

## Output Example

```
🟢 GOOGL | Score: 8/10 | BULLISH 🔥
   Summary: Strong AI infrastructure investments and cloud growth drive positive sentiment
   Confidence: high
💾 Successfully saved GOOGL signal to database (ID: 955629ea-baee-4d31-95c5-67b139795dbb)
```

## Logging

The scheduler creates detailed logs in `scheduler.log` and console output, including:
- Job start/end times
- Duration tracking  
- Success/failure status
- Database save confirmations
- Error handling

## Cost Optimization

- Uses Claude Haiku 4.5 for low-cost sentiment analysis
- Limits to 20 most recent articles per ticker
- Efficient API usage with proper error handling