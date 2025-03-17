import requests
import json
import boto3
import os
import time
import psycopg2
import psycopg2.extras
from datetime import datetime
import signal
import sys
import pickle
from dotenv import load_dotenv

load_dotenv()

# AWS S3 configuration
s3_client = boto3.client('s3')
RAW_BUCKET = os.getenv('RAW_BUCKET')
MEDIA_BUCKET = os.getenv('MEDIA_BUCKET')

# Database connection
db_params = {
    'dbname': os.getenv('DB_NAME'),
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
    'host': os.getenv('DB_HOST'),
    'port': os.getenv('DB_PORT', '5432')
}

# iFixit API base URL
API_BASE_URL = "https://www.ifixit.com/api/2.0"

# Checkpoint file to save progress
CHECKPOINT_FILE = "fetch_checkpoint.pkl"
STATS_FILE = "fetch_stats.json"

# Global variables for tracking progress
current_offset = 0
guides_processed = 0
media_downloaded = 0
start_time = datetime.now()
last_checkpoint_time = datetime.now()
checkpoint_interval = 60  # seconds between checkpoints
stats_interval = 300  # seconds between stats updates

# Function to save checkpoint
def save_checkpoint():
    global current_offset, guides_processed, media_downloaded, last_checkpoint_time
    
    checkpoint_data = {
        'offset': current_offset,
        'guides_processed': guides_processed,
        'media_downloaded': media_downloaded,
        'timestamp': datetime.now().isoformat()
    }
    
    try:
        with open(CHECKPOINT_FILE, 'wb') as f:
            pickle.dump(checkpoint_data, f)
        print(f"Checkpoint saved at offset {current_offset}, {guides_processed} guides processed")
        last_checkpoint_time = datetime.now()
    except Exception as e:
        print(f"Error saving checkpoint: {e}")

# Function to load checkpoint
def load_checkpoint():
    global current_offset, guides_processed, media_downloaded
    
    if os.path.exists(CHECKPOINT_FILE):
        try:
            with open(CHECKPOINT_FILE, 'rb') as f:
                checkpoint_data = pickle.load(f)
                current_offset = checkpoint_data.get('offset', 0)
                guides_processed = checkpoint_data.get('guides_processed', 0)
                media_downloaded = checkpoint_data.get('media_downloaded', 0)
                timestamp = checkpoint_data.get('timestamp', 'unknown')
                print(f"Loaded checkpoint from {timestamp}")
                print(f"Resuming from offset {current_offset}, {guides_processed} guides processed")
                return True
        except Exception as e:
            print(f"Error loading checkpoint: {e}")
    
    print("No checkpoint found, starting from beginning")
    return False

# Function to update stats
def update_stats():
    global guides_processed, media_downloaded, start_time
    
    current_time = datetime.now()
    elapsed_seconds = (current_time - start_time).total_seconds()
    hours = elapsed_seconds // 3600
    minutes = (elapsed_seconds % 3600) // 60
    seconds = elapsed_seconds % 60
    
    guides_per_hour = (guides_processed / elapsed_seconds) * 3600 if elapsed_seconds > 0 else 0
    
    stats = {
        'timestamp': current_time.isoformat(),
        'elapsed_time': f"{int(hours)}h {int(minutes)}m {int(seconds)}s",
        'guides_processed': guides_processed,
        'media_downloaded': media_downloaded,
        'current_offset': current_offset,
        'guides_per_hour': round(guides_per_hour, 2),
        'est_completion_time': f"{round(1000000 / guides_per_hour if guides_per_hour > 0 else 0, 1)} hours"
    }
    
    try:
        with open(STATS_FILE, 'w') as f:
            json.dump(stats, f, indent=2)
    except Exception as e:
        print(f"Error saving stats: {e}")
    
    return stats

# Function to display current progress
def display_progress():
    stats = update_stats()
    print("\n--- PROGRESS UPDATE ---")
    print(f"Time elapsed: {stats['elapsed_time']}")
    print(f"Current offset: {stats['current_offset']}")
    print(f"Guides processed: {stats['guides_processed']}")
    print(f"Media files downloaded: {stats['media_downloaded']}")
    print(f"Processing rate: {stats['guides_per_hour']} guides/hour")
    print(f"Estimated completion time: {stats['est_completion_time']}")
    print("------------------------\n")

# Signal handler for graceful shutdown
def signal_handler(sig, frame):
    print("\nReceived shutdown signal. Saving checkpoint and exiting...")
    save_checkpoint()
    sys.exit(0)

# Register signal handler
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# Function to fetch guides with pagination
def fetch_guides(limit=20, offset=0):
    url = f"{API_BASE_URL}/guides?limit={limit}&offset={offset}"
    print(f"Fetching guides from {url}")
    try:
        response = requests.get(url)
        if response.status_code == 200:
            return response.json()
        else:
            print(f"Error fetching guides: {response.status_code}")
            return []
    except Exception as e:
        print(f"Exception when fetching guides: {e}")
        return []

# Function to fetch a specific guide
def fetch_guide(guide_id):
    url = f"{API_BASE_URL}/guides/{guide_id}"
    print(f"Fetching guide details from {url}")
    try:
        response = requests.get(url)
        if response.status_code == 200:
            return response.json()
        else:
            print(f"Error fetching guide {guide_id}: {response.status_code}")
            return None
    except Exception as e:
        print(f"Exception when fetching guide {guide_id}: {e}")
        return None

# Function to fetch tags for a guide
def fetch_guide_tags(guide_id):
    url = f"{API_BASE_URL}/guides/{guide_id}/tags"
    print(f"Fetching guide tags from {url}")
    try:
        response = requests.get(url)
        if response.status_code == 200:
            return response.json()
        else:
            print(f"Error fetching tags for guide {guide_id}: {response.status_code}")
            return []
    except Exception as e:
        print(f"Exception when fetching tags for guide {guide_id}: {e}")
        return []

# Function to download media
def download_media(url, media_type, media_id):
    global media_downloaded
    
    try:
        print(f"Downloading media: {url}")
        response = requests.get(url, stream=True)
        if response.status_code == 200:
            file_extension = url.split('.')[-1] if '.' in url else 'jpg'
            s3_path = f"ifixit/{media_type}/{media_id}/original.{file_extension}"
            
            s3_client.put_object(
                Bucket=MEDIA_BUCKET,
                Key=s3_path,
                Body=response.content
            )
            print(f"Saved media to S3: {s3_path}")
            media_downloaded += 1
            return s3_path
        else:
            print(f"Error downloading media {url}: {response.status_code}")
            return None
    except Exception as e:
        print(f"Error processing media {url}: {e}")
        return None

# Function to store guide in database
def store_guide_in_db(guide_data, guide_details, tags, conn):
    try:
        cursor = conn.cursor()
        
        # Insert guide
        cursor.execute("""
            INSERT INTO guides 
            (source_id, external_id, title, subject, type, difficulty, category, locale, raw_data)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (source_id, external_id) 
            DO UPDATE SET 
                title = EXCLUDED.title,
                subject = EXCLUDED.subject,
                type = EXCLUDED.type,
                difficulty = EXCLUDED.difficulty,
                category = EXCLUDED.category,
                locale = EXCLUDED.locale,
                raw_data = EXCLUDED.raw_data,
                updated_at = CURRENT_TIMESTAMP
            RETURNING id
        """, (
            1,  # source_id for iFixit
            str(guide_data.get('guideid', '')),
            guide_data.get('title', ''),
            guide_data.get('subject', ''),
            guide_data.get('type', ''),
            guide_details.get('difficulty', ''),
            guide_data.get('category', ''),
            guide_data.get('locale', 'en'),
            json.dumps(guide_details) if guide_details else None
        ))
        
        guide_id = cursor.fetchone()[0]
        print(f"Stored/updated guide in database with ID: {guide_id}")
        
        # Process steps if available
        if guide_details and 'steps' in guide_details:
            for step in guide_details['steps']:
                try:
                    cursor.execute("""
                        INSERT INTO steps
                        (guide_id, external_id, orderby, title, raw_data)
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (guide_id, external_id) 
                        DO UPDATE SET 
                            orderby = EXCLUDED.orderby,
                            title = EXCLUDED.title,
                            raw_data = EXCLUDED.raw_data,
                            updated_at = CURRENT_TIMESTAMP
                        RETURNING id
                    """, (
                        guide_id,
                        str(step.get('stepid', '')),
                        step.get('orderby', 0),
                        step.get('title', ''),
                        json.dumps(step)
                    ))
                    
                    step_id = cursor.fetchone()[0]
                    print(f"Stored/updated step with ID: {step_id}")
                    
                    # Process media for step
                    if 'media' in step and 'data' in step['media']:
                        for media_item in step['media']['data']:
                            if 'original' in media_item:
                                try:
                                    media_type = 'images'
                                    s3_path = download_media(
                                        media_item['original'], 
                                        media_type, 
                                        media_item['id']
                                    )
                                    
                                    if s3_path:
                                        cursor.execute("""
                                            INSERT INTO media
                                            (guide_id, step_id, media_type, external_id, original_url, s3_path, metadata)
                                            VALUES (%s, %s, %s, %s, %s, %s, %s)
                                            ON CONFLICT (guide_id, step_id, external_id) 
                                            DO UPDATE SET 
                                                original_url = EXCLUDED.original_url,
                                                s3_path = EXCLUDED.s3_path
                                            RETURNING id
                                        """, (
                                            guide_id,
                                            step_id,
                                            media_type,
                                            str(media_item['id']),
                                            media_item['original'],
                                            s3_path,
                                            json.dumps(media_item)
                                        ))
                                        
                                        media_id = cursor.fetchone()[0]
                                        print(f"Stored/updated media with ID: {media_id}")
                                except Exception as e:
                                    print(f"Error processing step media: {e}")
                except Exception as e:
                    print(f"Error processing step: {e}")
        
        # Process guide image
        if 'image' in guide_data and 'original' in guide_data['image']:
            try:
                media_type = 'images'
                s3_path = download_media(
                    guide_data['image']['original'], 
                    media_type, 
                    guide_data['image']['id']
                )
                
                if s3_path:
                    cursor.execute("""
                        INSERT INTO media
                        (guide_id, step_id, media_type, external_id, original_url, s3_path, metadata)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (guide_id, step_id, external_id) 
                        DO UPDATE SET 
                            original_url = EXCLUDED.original_url,
                            s3_path = EXCLUDED.s3_path
                        RETURNING id
                    """, (
                        guide_id,
                        None,  # No step_id for guide main image
                        media_type,
                        str(guide_data['image']['id']),
                        guide_data['image']['original'],
                        s3_path,
                        json.dumps(guide_data['image'])
                    ))
                    
                    media_id = cursor.fetchone()[0]
                    print(f"Stored/updated guide main image with ID: {media_id}")
            except Exception as e:
                print(f"Error processing guide main image: {e}")
        
        # Process tags
        for tag_name in tags:
            try:
                # Insert or get tag
                cursor.execute("""
                    INSERT INTO tags (name)
                    VALUES (%s)
                    ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name
                    RETURNING id
                """, (tag_name,))
                tag_id = cursor.fetchone()[0]
                
                # Link tag to guide
                cursor.execute("""
                    INSERT INTO guide_tags (guide_id, tag_id)
                    VALUES (%s, %s)
                    ON CONFLICT DO NOTHING
                """, (guide_id, tag_id))
                
                print(f"Added tag '{tag_name}' to guide")
            except Exception as e:
                print(f"Error processing tag '{tag_name}': {e}")
        
        conn.commit()
        return guide_id
    except Exception as e:
        conn.rollback()
        print(f"Error storing guide in database: {e}")
        return None

# Main function
def main():
    global current_offset, guides_processed, media_downloaded, start_time, last_checkpoint_time
    
    print(f"Starting iFixit data fetcher at {datetime.now()}")
    
    # Load checkpoint if exists
    if load_checkpoint():
        # Checkpoint found, current_offset has been updated
        pass
    else:
        # No checkpoint, start from beginning
        current_offset = 0
        guides_processed = 0
        media_downloaded = 0
    
    # Record start time
    start_time = datetime.now()
    last_checkpoint_time = datetime.now()
    
    # Use a very large number to effectively fetch all guides
    total_to_process = 1000000
    
    try:
        conn = psycopg2.connect(**db_params)
        print("Connected to database successfully")
        
        batch_size = 20  # Number of guides to fetch per API call
        
        while current_offset < total_to_process:
            guides = fetch_guides(limit=batch_size, offset=current_offset)
            
            if not guides:
                print(f"No guides returned for offset {current_offset}, stopping")
                break
                
            print(f"Fetched {len(guides)} guides")
            
            # Store raw guide list data in S3
            try:
                s3_client.put_object(
                    Bucket=RAW_BUCKET,
                    Key=f"ifixit/guides/list/{current_offset}-{current_offset+batch_size}.json",
                    Body=json.dumps(guides)
                )
                print(f"Saved guide list to S3 for offset {current_offset}")
            except Exception as e:
                print(f"Error saving guide list to S3: {e}")
            
            for guide in guides:
                guide_id = guide.get('guideid')
                if not guide_id:
                    continue
                    
                print(f"Processing guide {guide_id}: {guide.get('title', 'No title')}")
                
                # Fetch detailed guide info
                guide_details = fetch_guide(guide_id)
                
                if guide_details:
                    # Store raw guide details in S3
                    try:
                        s3_client.put_object(
                            Bucket=RAW_BUCKET,
                            Key=f"ifixit/guides/{guide_id}/details.json",
                            Body=json.dumps(guide_details)
                        )
                        print(f"Saved guide details to S3 for guide {guide_id}")
                    except Exception as e:
                        print(f"Error saving guide details to S3: {e}")
                    
                    # Fetch tags
                    tags = fetch_guide_tags(guide_id)
                    
                    if tags:
                        # Store tags in S3
                        try:
                            s3_client.put_object(
                                Bucket=RAW_BUCKET,
                                Key=f"ifixit/guides/{guide_id}/tags.json",
                                Body=json.dumps(tags)
                            )
                            print(f"Saved guide tags to S3 for guide {guide_id}")
                        except Exception as e:
                            print(f"Error saving guide tags to S3: {e}")
                    
                    # Store in database
                    db_guide_id = store_guide_in_db(guide, guide_details, tags, conn)
                    if db_guide_id:
                        guides_processed += 1
                        print(f"Successfully processed guide {guide_id}")
                    
                # Check if it's time to save a checkpoint
                now = datetime.now()
                if (now - last_checkpoint_time).total_seconds() >= checkpoint_interval:
                    save_checkpoint()
                    
                # Check if it's time to display progress stats
                if (now - last_checkpoint_time).total_seconds() >= stats_interval:
                    display_progress()
                
                # Be nice to the API - add small delay between requests
                time.sleep(2)
            
            # Update offset for next batch
            current_offset += len(guides)
            print(f"Processed guides {current_offset - len(guides)} to {current_offset}")
            
            # Save checkpoint after each batch
            save_checkpoint()
            
            # Display progress after each batch
            display_progress()
    except Exception as e:
        print(f"Error in main process: {e}")
        # Save checkpoint in case of error
        save_checkpoint()
    finally:
        if 'conn' in locals() and conn:
            conn.close()
            print("Database connection closed")
    
    print(f"Completed iFixit data fetcher at {datetime.now()}")
    print(f"Total guides processed: {guides_processed}")
    print(f"Total media downloaded: {media_downloaded}")

if __name__ == "__main__":
    main()
