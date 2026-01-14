import os
import re
from dotenv import load_dotenv
from googleapiclient.discovery import build

def main():
    # Load environment variables
    load_dotenv()
    api_key = os.getenv("YOUTUBE_API_KEY")

    if not api_key or api_key == "YOUR_API_KEY_HERE":
        print("Error: Please set your YOUTUBE_API_KEY in the .env file.")
        return

    try:
        # Build the YouTube service
        youtube = build('youtube', 'v3', developerKey=api_key)

        print("Searching for 5 channels with >= 10,000 subscribers...")
        
        channels_found_count = 0
        next_page_token = None
        
        seen_channel_ids = set()
        
        # Keep searching until we find 5 qualified channels
        while channels_found_count < 5:
            # 1. Search for channels (Batch of 50 to maximize hit rate)
            request = youtube.search().list(
                part="snippet",
                maxResults=30,
                order="viewCount",
                type="channel",
                q="발로란트", # Keywords: Fashion, Lookbook, Outfit
                regionCode="KR", # Filter for South Korea
                relevanceLanguage="ko", # Filter for Korean language
                pageToken=next_page_token
            )
            response = request.execute()
            
            search_items = response.get('items', [])
            if not search_items:
                print("No more channels found.")
                break
                
            # Collect Channel IDs from search results
            channel_ids = []
            for item in search_items:
                cid = item['id']['channelId']
                if cid not in seen_channel_ids:
                    channel_ids.append(cid)
                    seen_channel_ids.add(cid)
            
            if not channel_ids:
                next_page_token = response.get('nextPageToken')
                if not next_page_token:
                    break
                continue

            # 2. Get Channel Details (Statistics & Full Description)
            stats_request = youtube.channels().list(
                part="statistics,snippet",
                id=",".join(channel_ids)
            )
            stats_response = stats_request.execute()
            
            # 3. Filter and Print
            for item in stats_response.get('items', []):
                if channels_found_count >= 5:
                    print("Found 5 channels. Exiting.")
                    return
                
                # Check Subscriber Count
                subscriber_count_str = item['statistics'].get('subscriberCount', '0')
                if not subscriber_count_str.isdigit():
                    continue
                    
                subscriber_count = int(subscriber_count_str)
                
                # Check Country (Relaxed Filter)
                country = item['snippet'].get('country')
                if country and country != 'KR':
                    continue

                if subscriber_count >= 10000:
                    channels_found_count += 1
                    
                    channel_title = item['snippet']['title']
                    full_description = item['snippet'].get('description', '')
                    channel_id = item['id']
                    
                    # Extract email from full description
                    emails = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', full_description)
                    email_text = ", ".join(set(emails)) if emails else "None found"
                    
                    print(f"[{channels_found_count}/5] Found Channel")
                    print(f"Name: {channel_title}")
                    print(f"ID: {channel_id}")
                    print(f"Subscribers: {subscriber_count:,}")
                    print(f"Emails: {email_text}")
                    print(f"Description: {full_description[:100]}...")
                    print("-" * 30)
            
            # Pagination
            next_page_token = response.get('nextPageToken')
            if not next_page_token:
                print("Reached end of search results.")
                break

        if channels_found_count < 5:
            print(f"Wrapped up. Total candidates found: {channels_found_count}")

    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    main()
