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

# Load environment variables
load_dotenv()

# Configuration
WATCHLIST = [
    'AAPL', 'NVDA', 'MSFT', 'GOOGL', 'AMZN', 
    'META', 'TSLA', 'JPM', 'V', 'AMD'
]

FINNHUB_API_KEY = os.getenv('FINNHUB_API_KEY')
ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY')

# Initialize Anthropic client
client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

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

def main():
    """
    Main function to analyze sentiment for all tickers in the watchlist.
    """
    print("🤖 Stock Signal Engine Starting...")
    print(f"📊 Analyzing {len(WATCHLIST)} tickers: {', '.join(WATCHLIST)}")
    print("=" * 80)
    
    results = []
    
    for ticker in WATCHLIST:
        print(f"\n📈 Processing {ticker}...")
        
        # Get news articles
        news_articles = get_news(ticker)
        
        # Analyze sentiment
        sentiment = score_sentiment(ticker, news_articles)
        results.append(sentiment)
        
        # Print results
        print(format_sentiment_output(sentiment))
    
    print("=" * 80)
    print("🎯 Analysis Complete!")
    
    # Summary statistics
    bullish_count = sum(1 for r in results if r['direction'] == 'bullish')
    bearish_count = sum(1 for r in results if r['direction'] == 'bearish')
    neutral_count = sum(1 for r in results if r['direction'] == 'neutral')
    
    print(f"\n📊 Summary:")
    print(f"   🟢 Bullish: {bullish_count}")
    print(f"   🔴 Bearish: {bearish_count}")
    print(f"   🟡 Neutral: {neutral_count}")
    
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