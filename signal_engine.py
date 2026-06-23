#!/usr/bin/env python3
"""
Stock Signal Engine
Analyzes news sentiment for a watchlist of stocks using Finnhub API and Claude AI.
"""

import os
import json
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Any
from dotenv import load_dotenv
import anthropic
from supabase import create_client, Client

# Load environment variables
load_dotenv()

# Configuration
WATCHLIST = [
    # Mega cap tech
    'AAPL', 'NVDA', 'MSFT', 'GOOGL', 'AMZN', 'META', 'TSLA',
    # Financials
    'JPM', 'V', 'MA', 'BAC', 'GS',
    # Semiconductors
    'AMD', 'INTC', 'AVGO', 'TSM',
    # Consumer
    'WMT', 'COST', 'NKE', 'MCD',
    # Healthcare
    'JNJ', 'UNH', 'PFE',
    # Energy
    'XOM', 'CVX',
    # ETFs for macro signal
    'SPY', 'QQQ',
    # High momentum
    'PLTR', 'COIN', 'SNOW'
]

FINNHUB_API_KEY = os.getenv('FINNHUB_API_KEY')
ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY')
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_SECRET_KEY = os.getenv('SUPABASE_SECRET_KEY')

# Initialize clients
client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_SECRET_KEY)

# Cache for SPY data to avoid multiple API calls
spy_cache = {'data': None, 'timestamp': None}

def get_news(ticker: str) -> List[Dict[str, Any]]:
    """
    Fetch company news from Finnhub API for the last 7 days.
    
    Args:
        ticker (str): Stock ticker symbol
        
    Returns:
        List[Dict]: List of news articles with headline, summary, datetime, etc.
    """
    if not FINNHUB_API_KEY:
        raise ValueError("FINNHUB_API_KEY not found in environment variables")
    
    # Calculate date range (last 7 days)
    end_date = datetime.now()
    start_date = end_date - timedelta(days=7)
    
    # Format dates for API (YYYY-MM-DD)
    from_date = start_date.strftime('%Y-%m-%d')
    to_date = end_date.strftime('%Y-%m-%d')
    
    # Finnhub company news endpoint
    url = "https://finnhub.io/api/v1/company-news"
    params = {
        'symbol': ticker,
        'from': from_date,
        'to': to_date,
        'token': FINNHUB_API_KEY
    }
    
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        
        news_data = response.json()
        
        # Filter and format news articles
        articles = []
        for article in news_data[:20]:  # Limit to 20 most recent articles
            if article.get('headline') and article.get('summary'):
                articles.append({
                    'headline': article['headline'],
                    'summary': article['summary'],
                    'datetime': datetime.fromtimestamp(article['datetime']).isoformat(),
                    'source': article.get('source', 'Unknown'),
                    'url': article.get('url', '')
                })
        
        print(f"✓ Found {len(articles)} news articles for {ticker}")
        return articles
        
    except requests.exceptions.RequestException as e:
        print(f"✗ Error fetching news for {ticker}: {e}")
        return []
    except Exception as e:
        print(f"✗ Unexpected error for {ticker}: {e}")
        return []

def score_sentiment(ticker: str, news_articles: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Analyze sentiment of news articles using Claude AI.
    
    Args:
        ticker (str): Stock ticker symbol
        news_articles (List[Dict]): List of news articles to analyze
        
    Returns:
        Dict: Sentiment analysis results
    """
    if not ANTHROPIC_API_KEY:
        raise ValueError("ANTHROPIC_API_KEY not found in environment variables")
    
    if not news_articles:
        return {
            'ticker': ticker,
            'sentiment_score': 5,
            'direction': 'neutral',
            'confidence': 'low',
            'summary': 'No recent news articles found for analysis'
        }
    
    # Prepare news content for analysis
    news_content = []
    for article in news_articles:
        news_content.append(f"Headline: {article['headline']}")
        news_content.append(f"Summary: {article['summary']}")
        news_content.append("---")
    
    news_text = "\n".join(news_content)
    
    prompt = f"""
Analyze the following news articles for {ticker} and provide a sentiment analysis.

News Articles:
{news_text}

Please analyze the overall sentiment and return a JSON object with exactly these fields:
- ticker: "{ticker}"
- sentiment_score: A number from 1-10 (1=very bearish, 5=neutral, 10=very bullish)
- direction: "bullish", "bearish", or "neutral"
- confidence: "low", "medium", or "high"
- summary: One sentence explaining your analysis

Only return the JSON object, no additional text.
"""

    try:
        message = client.messages.create(
            model="claude-haiku-4-5",  # Using Claude Haiku for cost efficiency
            max_tokens=300,
            messages=[{
                "role": "user",
                "content": prompt
            }]
        )
        
        # Parse the JSON response
        response_text = message.content[0].text.strip()
        
        # Clean up response if it has extra formatting
        if response_text.startswith('```json'):
            response_text = response_text.replace('```json', '').replace('```', '').strip()
        
        sentiment_data = json.loads(response_text)
        
        print(f"✓ Sentiment analysis completed for {ticker}")
        return sentiment_data
        
    except json.JSONDecodeError as e:
        print(f"✗ Error parsing sentiment response for {ticker}: {e}")
        return {
            'ticker': ticker,
            'sentiment_score': 5,
            'direction': 'neutral',
            'confidence': 'low',
            'summary': 'Unable to parse sentiment analysis'
        }
    except Exception as e:
        print(f"✗ Error analyzing sentiment for {ticker}: {e}")
        return {
            'ticker': ticker,
            'sentiment_score': 5,
            'direction': 'neutral',
            'confidence': 'low',
            'summary': f'Error during analysis: {str(e)}'
        }

def save_signal_to_db(sentiment: Dict[str, Any], article_count: int, run_id: str = "unknown") -> bool:
    """
    Save sentiment analysis result to Supabase signals table.
    
    Args:
        sentiment (Dict): Sentiment analysis results
        article_count (int): Number of articles analyzed
        run_id (str): Unique run identifier for debugging duplicates
        
    Returns:
        bool: True if successful, False otherwise
    """
    if not SUPABASE_URL or not SUPABASE_SECRET_KEY:
        print(f"✗ Supabase credentials not found, skipping database save for {sentiment['ticker']}")
        return False
    
    try:
        # Prepare data for insertion
        signal_data = {
            'ticker': sentiment['ticker'],
            'sentiment_score': sentiment['sentiment_score'],
            'direction': sentiment['direction'],
            'confidence': sentiment['confidence'],
            'summary': sentiment['summary'],
            'article_count': article_count,
            'created_at': datetime.now().isoformat()
        }
        
        # Insert into Supabase
        result = supabase.table('signals').insert(signal_data).execute()
        
        if result.data:
            print(f"💾 [RUN:{run_id}] Successfully saved {sentiment['ticker']} signal to database (ID: {result.data[0].get('id', 'unknown')})")
            return True
        else:
            print(f"✗ [RUN:{run_id}] Failed to save {sentiment['ticker']} signal to database")
            return False
            
    except Exception as e:
        print(f"✗ [RUN:{run_id}] Database error for {sentiment['ticker']}: {e}")
        return False

def format_sentiment_output(sentiment: Dict[str, Any]) -> str:
    """Format sentiment analysis for console output."""
    direction_emoji = {
        'bullish': '🟢',
        'bearish': '🔴', 
        'neutral': '🟡'
    }
    
    confidence_emoji = {
        'high': '🔥',
        'medium': '👍',
        'low': '🤷'
    }
    
    return f"""
{direction_emoji.get(sentiment['direction'], '⚪')} {sentiment['ticker']} | Score: {sentiment['sentiment_score']}/10 | {sentiment['direction'].upper()} {confidence_emoji.get(sentiment['confidence'], '')}
   Summary: {sentiment['summary']}
   Confidence: {sentiment['confidence']}
"""

def check_market_regime() -> bool:
    """
    Check if market regime allows new bullish entries by comparing SPY to its 5-day SMA.
    
    Returns:
        bool: True if SPY is above 5-day SMA (bullish regime), False otherwise
    """
    global spy_cache
    
    try:
        # Check cache first (valid for 1 hour)
        now = datetime.now()
        if (spy_cache['data'] is not None and 
            spy_cache['timestamp'] is not None and 
            (now - spy_cache['timestamp']).seconds < 3600):
            
            spy_data = spy_cache['data']
            print("📊 Using cached SPY data for market regime check")
        else:
            # Fetch fresh SPY data from Finnhub
            print("📊 Fetching SPY data for market regime analysis...")
            
            # Calculate date range for last 6 days (to get 5 trading days)
            end_date = datetime.now()
            start_date = end_date - timedelta(days=10)  # Extra buffer for weekends
            
            # Format dates for Finnhub API (YYYY-MM-DD)
            from_date = int(start_date.timestamp())
            to_date = int(end_date.timestamp())
            
            # Finnhub stock candles endpoint for SPY
            url = "https://finnhub.io/api/v1/stock/candle"
            params = {
                'symbol': 'SPY',
                'resolution': 'D',  # Daily
                'from': from_date,
                'to': to_date,
                'token': FINNHUB_API_KEY
            }
            
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            
            spy_data = response.json()
            
            # Cache the data
            spy_cache['data'] = spy_data
            spy_cache['timestamp'] = now
            
        # Validate response
        if spy_data.get('s') != 'ok' or not spy_data.get('c'):
            print("⚠️ Invalid SPY data received, proceeding with bullish entries (fail-safe)")
            return True
            
        # Get last 5 closing prices
        closes = spy_data['c'][-5:]  # Last 5 closes
        
        if len(closes) < 5:
            print(f"⚠️ Only {len(closes)} days of SPY data available, proceeding with bullish entries (fail-safe)")
            return True
            
        # Calculate 5-day simple moving average
        sma_5 = sum(closes) / len(closes)
        current_price = closes[-1]  # Most recent close
        
        # Determine market regime
        is_bullish_regime = current_price >= sma_5
        
        print(f"📊 SPY Market Regime Analysis:")
        print(f"   💰 Current SPY Price: ${current_price:.2f}")
        print(f"   📈 5-Day SMA: ${sma_5:.2f}")
        print(f"   📊 Price vs SMA: {current_price - sma_5:+.2f} ({((current_price - sma_5) / sma_5 * 100):+.1f}%)")
        
        if is_bullish_regime:
            print(f"   🟢 Market Regime: BULLISH (SPY above SMA) - New long entries ALLOWED")
        else:
            print(f"   🔴 Market Regime: BEARISH (SPY below SMA) - New long entries BLOCKED")
            
        return is_bullish_regime
        
    except requests.exceptions.RequestException as e:
        print(f"⚠️ Error fetching SPY data: {e}")
        print("⚠️ Proceeding with bullish entries (fail-safe)")
        return True
    except Exception as e:
        print(f"⚠️ Unexpected error in market regime check: {e}")
        print("⚠️ Proceeding with bullish entries (fail-safe)")
        return True

def main():
    """
    Main function to analyze sentiment for all tickers in the watchlist.
    """
    # Generate unique run ID for this execution
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]  # YYYYMMDD_HHMMSS_mmm
    
    print("🤖 Stock Signal Engine Starting...")
    print(f"🆔 Run ID: {run_id}")
    print(f"📊 Analyzing {len(WATCHLIST)} tickers: {', '.join(WATCHLIST)}")
    print("=" * 80)
    
    # Check market regime before processing signals
    is_bullish_market = check_market_regime()
    print("=" * 80)
    
    results = []
    
    for ticker in WATCHLIST:
        print(f"\n📈 Processing {ticker}...")
        
        # Get news articles
        news_articles = get_news(ticker)
        
        # Analyze sentiment
        sentiment = score_sentiment(ticker, news_articles)
        results.append(sentiment)
        
        # Apply market regime filter for bullish signals
        should_save_signal = True
        if sentiment['direction'] == 'bullish' and not is_bullish_market:
            print(f"   🚫 Market regime bearish (SPY below 5-day SMA) - BLOCKING bullish signal for {ticker}")
            should_save_signal = False
        
        # Save to database if sentiment analysis was successful and passes regime filter
        if should_save_signal:
            article_count = len(news_articles)
            save_signal_to_db(sentiment, article_count, run_id)
        else:
            print(f"   ⚠️ Bullish signal for {ticker} not saved due to bearish market regime")
        
        # Print results
        print(format_sentiment_output(sentiment))
    
    print("=" * 80)
    print("🎯 Analysis Complete!")
    
    # Summary statistics
    bullish_analyzed = sum(1 for r in results if r['direction'] == 'bullish')
    bearish_count = sum(1 for r in results if r['direction'] == 'bearish')
    neutral_count = sum(1 for r in results if r['direction'] == 'neutral')
    
    # Calculate how many bullish signals were actually saved
    bullish_saved = bullish_analyzed if is_bullish_market else 0
    bullish_blocked = bullish_analyzed - bullish_saved
    
    print(f"\n📊 Summary:")
    print(f"   🟢 Bullish Analyzed: {bullish_analyzed}")
    if bullish_blocked > 0:
        print(f"   🚫 Bullish Blocked (Market Regime): {bullish_blocked}")
    print(f"   ✅ Bullish Saved: {bullish_saved}")
    print(f"   🔴 Bearish: {bearish_count}")
    print(f"   🟡 Neutral: {neutral_count}")
    
    if not is_bullish_market and bullish_analyzed > 0:
        print(f"\n⚠️ Market Regime Filter Active: {bullish_analyzed} bullish signals blocked from database")
    
    # Top performers
    top_bullish = sorted([r for r in results if r['direction'] == 'bullish'], 
                        key=lambda x: x['sentiment_score'], reverse=True)[:3]
    top_bearish = sorted([r for r in results if r['direction'] == 'bearish'], 
                        key=lambda x: x['sentiment_score'])[:3]
    
    if top_bullish:
        print(f"\n🚀 Most Bullish: {', '.join([r['ticker'] for r in top_bullish])}")
    if top_bearish:
        print(f"📉 Most Bearish: {', '.join([r['ticker'] for r in top_bearish])}")

if __name__ == "__main__":
    main()