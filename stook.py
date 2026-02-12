import asyncio
import aiohttp
import pandas as pd

BASE_URL = "https://groww.in/v1/api/stocks_data/v1/accord_points/exchange/NSE/segment/CASH/latest_prices_ohlc/{}"

# Read input CSV
df = pd.read_csv("ind_copy.csv")
symbols = df["Symbol"].dropna().tolist()

# Limit concurrent requests (safe for Groww)
SEM = asyncio.Semaphore(50)

async def fetch_price(session, symbol):
    async with SEM:
        url = BASE_URL.format(symbol)

        try:
            async with session.get(url) as response:
                data = await response.json()

                ltp_price = data.get("ltp")
                if ltp_price == 0:
                    return None
                return {
                    "Symbol": symbol,
                    "Price": ltp_price
                }

        except:
            return {
                "Symbol": symbol,
                "Price": None
            }


async def main():
   coun = 100 
   while(coun):
     async with aiohttp.ClientSession() as session:
        tasks = [fetch_price(session, symbol) for symbol in symbols]
        
        results = await asyncio.gather(*tasks)
        print(results)
 
        # Convert to DataFrame
        output_df = pd.DataFrame(results)

        # Save CSV
        output_df.to_csv("output_prices.csv", index=False)

        print("✅ Prices saved to output_prices.csv")
        coun-= 1
asyncio.run(main())
