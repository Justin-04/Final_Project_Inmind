"""Quick test for SerpAPI Google Search."""
import os
from dotenv import load_dotenv
from serpapi import GoogleSearch

load_dotenv()

API_KEY = os.getenv("SERPAPI_KEY")
print(f"SerpAPI Key: {API_KEY[:10]}...{API_KEY[-4:]}" if API_KEY else "❌ SERPAPI_KEY not set")

params = {
    "engine": "google",
    "q": "DJI Mini 4 Pro price",
    "api_key": API_KEY,
    "num": 5,
}

search = GoogleSearch(params)
results = search.get_dict()

if "error" in results:
    print(f"❌ Error: {results['error']}")
else:
    organic = results.get("organic_results", [])
    print(f"✅ Got {len(organic)} results\n")
    for r in organic[:5]:
        print(f"  {r.get('title')}")
        print(f"  {r.get('link')}")
        print(f"  {r.get('snippet', '')[:80]}")
        print()
