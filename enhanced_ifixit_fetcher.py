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
import urllib.parse

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
wikis_processed = 0
categories_processed = 0
media_downloaded = 0
start_time = datetime.now()
last_checkpoint_time = datetime.now()
checkpoint_interval = 60  # seconds between checkpoints
stats_interval = 300  # seconds between stats updates

# Function to save checkpoint
def save_checkpoint():
    global current_offset, guides_processed, wikis_processed, categories_processed, media_downloaded, last_checkpoint_time
    
    checkpoint_data = {
        'offset': current_offset,
        'guides_processed': guides_processed,
        'wikis_processed': wikis_processed,
        'categories_processed': categories_processed,
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
    global current_offset, guides_processed, wikis_processed, categories_processed, media_downloaded
    
    if os.path.exists(CHECKPOINT_FILE):
        try:
            with open(CHECKPOINT_FILE, 'rb') as f:
                checkpoint_data = pickle.load(f)
                current_offset = checkpoint_data.get('offset', 0)
                guides_processed = checkpoint_data.get('guides_processed', 0)
                wikis_processed = checkpoint_data.get('wikis_processed', 0)
                categories_processed = checkpoint_data.get('categories_processed', 0)
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
    global guides_processed, wikis_processed, categories_processed, media_downloaded, start_time
    
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
        'wikis_processed': wikis_processed,
        'categories_processed': categories_processed,
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
    print(f"Wikis processed: {stats['wikis_processed']}")
    print(f"Categories processed: {stats['categories_processed']}")
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

# Function to make an API request with retries
def make_api_request(url, max_retries=3, retry_delay=5):
    retries = 0
    while retries < max_retries:
        try:
            print(f"Requesting: {url}")
            response = requests.get(url)
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 429:  # Rate limited
                retry_delay = int(response.headers.get('Retry-After', retry_delay * 2))
                print(f"Rate limited. Waiting {retry_delay} seconds before retry.")
            else:
                print(f"API Error: {response.status_code} - {response.text}")
            
            retries += 1
            if retries < max_retries:
                time.sleep(retry_delay)
                retry_delay *= 2  # Exponential backoff
        except Exception as e:
            print(f"Request failed: {e}")
            retries += 1
            if retries < max_retries:
                time.sleep(retry_delay)
                retry_delay *= 2
    
    print(f"Failed after {max_retries} attempts: {url}")
    return None

# Function to fetch categories hierarchy
def fetch_categories_hierarchy():
    url = f"{API_BASE_URL}/categories"
    print(f"Fetching categories hierarchy from {url}")
    return make_api_request(url)

# Function to fetch wikis by namespace
def fetch_wikis(namespace, limit=20, offset=0):
    url = f"{API_BASE_URL}/wikis/{namespace}?limit={limit}&offset={offset}"
    print(f"Fetching wikis from {url}")
    return make_api_request(url)

# Function to fetch wiki details
def fetch_wiki_details(namespace, title):
    # URL encode the title to handle special characters
    encoded_title = urllib.parse.quote(title)
    url = f"{API_BASE_URL}/wikis/{namespace}/{encoded_title}"
    print(f"Fetching wiki details from {url}")
    return make_api_request(url)

# Function to fetch tags for a wiki
def fetch_wiki_tags(namespace, title):
    # URL encode the title to handle special characters
    encoded_title = urllib.parse.quote(title)
    url = f"{API_BASE_URL}/wikis/{namespace}/{encoded_title}/tags"
    print(f"Fetching wiki tags from {url}")
    return make_api_request(url)

# Function to fetch guides with pagination
def fetch_guides(limit=20, offset=0):
    url = f"{API_BASE_URL}/guides?limit={limit}&offset={offset}"
    print(f"Fetching guides from {url}")
    return make_api_request(url)

# Function to fetch a specific guide
def fetch_guide(guide_id):
    url = f"{API_BASE_URL}/guides/{guide_id}"
    print(f"Fetching guide details from {url}")
    return make_api_request(url)

# Function to fetch tags for a guide
def fetch_guide_tags(guide_id):
    url = f"{API_BASE_URL}/guides/{guide_id}/tags"
    print(f"Fetching guide tags from {url}")
    return make_api_request(url)

# Function to fetch product information
def fetch_product(itemcode, langid='en'):
    url = f"{API_BASE_URL}/cart/product/{itemcode}/{langid}"
    print(f"Fetching product info from {url}")
    return make_api_request(url)

# Function to fetch suggestions
def fetch_suggestions(query, doctypes='all'):
    # URL encode the query to handle special characters
    encoded_query = urllib.parse.quote(query)
    url = f"{API_BASE_URL}/suggest/{encoded_query}?doctypes={doctypes}"
    print(f"Fetching suggestions for '{query}' from {url}")
    return make_api_request(url)

# Function to fetch all tags
def fetch_all_tags(limit=100, offset=0, order='ASC'):
    url = f"{API_BASE_URL}/tags?limit={limit}&offset={offset}&order={order}"
    print(f"Fetching tags from {url}")
    return make_api_request(url)

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

# Function to process category hierarchy recursively
def process_category_hierarchy(hierarchy, parent_id=None, path=''):
    global categories_processed
    
    for title, children in hierarchy.items():
        try:
            # Create full path for this category
            current_path = f"{path}/{title}" if path else title
            
            # Insert or update category in database
            conn = psycopg2.connect(**db_params)
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO categories (title, display_title, category_path, parent_id) 
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (title, parent_id) DO UPDATE SET
                    display_title = EXCLUDED.display_title,
                    category_path = EXCLUDED.category_path,
                    updated_at = CURRENT_TIMESTAMP
                RETURNING id
            """, (title, title, current_path, parent_id))
            
            category_id = cursor.fetchone()[0]
            categories_processed += 1
            
            conn.commit()
            
            print(f"Processed category: {title} (ID: {category_id}, Path: {current_path})")
            
            # Process child categories recursively if any
            if children is not None:
                process_category_hierarchy(children, category_id, current_path)
            
        except Exception as e:
            print(f"Error processing category {title}: {e}")
            if 'conn' in locals() and conn:
                conn.rollback()
        finally:
            if 'cursor' in locals() and cursor:
                cursor.close()
            if 'conn' in locals() and conn:
                conn.close()

# Function to store wiki in database
def store_wiki_in_db(wiki_data, tags, conn):
    try:
        cursor = conn.cursor()
        
        # Check if this is a category wiki
        if wiki_data.get('namespace') == 'CATEGORY':
            # Try to find or update the existing category
            cursor.execute("""
                UPDATE categories
                SET wikiid = %s,
                    summary = %s,
                    namespace = %s,
                    raw_data = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE title = %s OR display_title = %s
                RETURNING id
            """, (
                wiki_data.get('wikiid'),
                wiki_data.get('summary'),
                wiki_data.get('namespace'),
                json.dumps(wiki_data),
                wiki_data.get('title'),
                wiki_data.get('display_title')
            ))
            
            result = cursor.fetchone()
            
            if not result:
                # If no category was updated, insert as new category
                cursor.execute("""
                    INSERT INTO categories
                    (title, display_title, wikiid, namespace, summary, raw_data)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING id
                """, (
                    wiki_data.get('title'),
                    wiki_data.get('display_title'),
                    wiki_data.get('wikiid'),
                    wiki_data.get('namespace'),
                    wiki_data.get('summary'),
                    json.dumps(wiki_data)
                ))
                
                category_id = cursor.fetchone()[0]
                print(f"Created new category from wiki: {wiki_data.get('title')} (ID: {category_id})")
            else:
                category_id = result[0]
                print(f"Updated existing category from wiki: {wiki_data.get('title')} (ID: {category_id})")
            
            # Process image if available
            if 'image' in wiki_data and wiki_data['image'] is not None and 'original' in wiki_data['image']:
                image_url = wiki_data['image']['original']
                s3_path = download_media(image_url, 'images', wiki_data['image']['id'])
                
                if s3_path:
                    # Update the category with the image URL
                    cursor.execute("""
                        UPDATE categories
                        SET image_url = %s
                        WHERE id = %s
                    """, (s3_path, category_id))
            
            # Add tags to the wiki
            if tags:
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
                        
                        # Link tag to wiki
                        cursor.execute("""
                            INSERT INTO wiki_tags (wiki_id, tag_id)
                            VALUES (%s, %s)
                            ON CONFLICT DO NOTHING
                        """, (wiki_data.get('wikiid'), tag_id))
                        
                        print(f"Added tag '{tag_name}' to wiki {wiki_data.get('wikiid')}")
                    except Exception as e:
                        print(f"Error processing tag '{tag_name}' for wiki: {e}")
        
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f"Error storing wiki in database: {e}")
        return False

# Function to store guide in database
def store_guide_in_db(guide_data, guide_details, tags, conn):
    try:
        cursor = conn.cursor()
        
        # Insert guide
        cursor.execute("""
            INSERT INTO guides 
            (source_id, external_id, title, subject, type, difficulty, category, locale, 
             flags, summary, public, modified_date, raw_data)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (source_id, external_id) 
            DO UPDATE SET 
                title = EXCLUDED.title,
                subject = EXCLUDED.subject,
                type = EXCLUDED.type,
                difficulty = EXCLUDED.difficulty,
                category = EXCLUDED.category,
                locale = EXCLUDED.locale,
                flags = EXCLUDED.flags,
                summary = EXCLUDED.summary,
                public = EXCLUDED.public,
                modified_date = EXCLUDED.modified_date,
                raw_data = EXCLUDED.raw_data,
                updated_at = CURRENT_TIMESTAMP
            RETURNING id
        """, (
            1,  # source_id for iFixit
            str(guide_data.get('guideid', '')),
            guide_data.get('title', ''),
            guide_data.get('subject', ''),
            guide_data.get('type', ''),
            guide_details.get('difficulty', {}).get('name') if guide_details and 'difficulty' in guide_details else None,
            guide_data.get('category', ''),
            guide_data.get('locale', 'en'),
            json.dumps(guide_data.get('flags', [])) if 'flags' in guide_data else None,
            guide_data.get('summary', ''),
            guide_data.get('public', True),
            guide_data.get('modified_date', 0),
            json.dumps(guide_details) if guide_details else None
        ))
        
        guide_id = cursor.fetchone()[0]
        print(f"Stored/updated guide in database with ID: {guide_id}")
        
        # Try to link guide to category
        if guide_data.get('category'):
            cursor.execute("""
                SELECT id FROM categories 
                WHERE title = %s OR display_title = %s
                LIMIT 1
            """, (guide_data.get('category'), guide_data.get('category')))
            
            result = cursor.fetchone()
            if result:
                category_id = result[0]
                cursor.execute("""
                    UPDATE guides
                    SET category_id = %s
                    WHERE id = %s
                """, (category_id, guide_id))
                print(f"Linked guide {guide_id} to category {category_id}")
        
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
        if 'image' in guide_data and guide_data['image'] and 'original' in guide_data['image']:
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
                    
                    # Update the guide with the image ID
                    cursor.execute("""
                        UPDATE guides 
                        SET image_id = %s
                        WHERE id = %s
                    """, (media_id, guide_id))
                    
                    print(f"Stored/updated guide main image with ID: {media_id}")
            except Exception as e:
                print(f"Error processing guide main image: {e}")
        
        # Process tags
        if tags:
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

# Function to store product information in database
def store_product_in_db(product_data, conn):
    try:
        cursor = conn.cursor()
        
        # Insert product
        cursor.execute("""
            INSERT INTO products
            (itemcode, productcode, title, raw_data)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (itemcode)
            DO UPDATE SET
                productcode = EXCLUDED.productcode,
                title = EXCLUDED.title,
                raw_data = EXCLUDED.raw_data,
                updated_at = CURRENT_TIMESTAMP
            RETURNING id
        """, (
            product_data.get('itemcode'),
            product_data.get('productcode'),
            product_data.get('title', 'Unknown Product'),
            json.dumps(product_data)
        ))
        
        product_id = cursor.fetchone()[0]
        print(f"Stored/updated product in database with ID: {product_id}")
        
        # Process related guides and wikis
        if 'related' in product_data:
            # Process related guides
            if 'guides' in product_data['related']:
                for guide_id, guide_info in product_data['related']['guides'].items():
                    try:
                        # Link guide to product
                        cursor.execute("""
                            INSERT INTO product_guides (product_id, guide_id)
                            VALUES (%s, (SELECT id FROM guides WHERE external_id = %s))
                            ON CONFLICT DO NOTHING
                        """, (product_id, guide_id))
                        print(f"Linked guide {guide_id} to product {product_id}")
                    except Exception as e:
                        print(f"Error linking guide {guide_id} to product: {e}")
            
            # Process related wikis
            if 'wikis' in product_data['related']:
                for wiki_id, wiki_info in product_data['related']['wikis'].items():
                    try:
                        # Link wiki to product
                        cursor.execute("""
                            INSERT INTO product_wikis (product_id, wiki_id)
                            VALUES (%s, %s)
                            ON CONFLICT DO NOTHING
                        """, (product_id, wiki_id))
                        print(f"Linked wiki {wiki_id} to product {product_id}")
                    except Exception as e:
                        print(f"Error linking wiki {wiki_id} to product: {e}")
        
        conn.commit()
        return product_id
    except Exception as e:
        conn.rollback()
        print(f"Error storing product in database: {e}")
        return None

# Function to fetch all categories and store them
def fetch_and_store_categories():
    try:
        # Fetch the categories hierarchy
        categories = fetch_categories_hierarchy()
        
        if categories:
            # Store raw categories data in S3
            try:
                s3_client.put_object(
                    Bucket=RAW_BUCKET,
                    Key=f"ifixit/categories/hierarchy_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                    Body=json.dumps(categories)
                )
                print("Saved categories hierarchy to S3")
            except Exception as e:
                print(f"Error saving categories hierarchy to S3: {e}")
            
            # Process each category
            conn = psycopg2.connect(**db_params)
            try:
                # Process the category hierarchy recursively
                process_category_hierarchy(categories)
                print(f"Processed {categories_processed} categories")
            finally:
                conn.close()
        else:
            print("No categories returned from API")
    except Exception as e:
        print(f"Error fetching categories: {e}")

# Function to fetch all wikis, store them and related data
def fetch_and_store_wikis(namespace='CATEGORY', batch_size=20):
    global wikis_processed
    
    offset = 0
    total_wikis = 0
    
    try:
        conn = psycopg2.connect(**db_params)
        
        while True:
            # Fetch a batch of wikis
            wikis = fetch_wikis(namespace, limit=batch_size, offset=offset)
            
            if not wikis or len(wikis) == 0:
                print(f"No more wikis returned for namespace {namespace}, stopping")
                break
            
            print(f"Fetched {len(wikis)} wikis for namespace {namespace}")
            
            # Store raw wikis list data in S3
            try:
                s3_client.put_object(
                    Bucket=RAW_BUCKET,
                    Key=f"ifixit/wikis/{namespace}/list/{offset}-{offset+len(wikis)}.json",
                    Body=json.dumps(wikis)
                )
            except Exception as e:
                print(f"Error saving wikis list to S3: {e}")
            
            # Process each wiki
            for wiki in wikis:
                wiki_id = wiki.get('wikiid')
                wiki_title = wiki.get('title')
                
                if not wiki_id or not wiki_title:
                    continue
                
                print(f"Processing wiki {wiki_id}: {wiki_title}")
                
                # Store current wiki data
                try:
                    # Fetch wiki tags
                    tags = fetch_wiki_tags(namespace, wiki_title)
                    
                    if tags:
                        # Store tags in S3
                        try:
                            s3_client.put_object(
                                Bucket=RAW_BUCKET,
                                Key=f"ifixit/wikis/{namespace}/{wiki_id}/tags.json",
                                Body=json.dumps(tags)
                            )
                        except Exception as e:
                            print(f"Error saving wiki tags to S3: {e}")
                    
                    # Store wiki in database
                    if store_wiki_in_db(wiki, tags, conn):
                        wikis_processed += 1
                        print(f"Successfully processed wiki {wiki_id}")
                except Exception as e:
                    print(f"Error processing wiki {wiki_id}: {e}")
                
                # Be nice to the API - add small delay between requests
                time.sleep(1)
            
            # Update offset for next batch
            offset += len(wikis)
            total_wikis += len(wikis)
            print(f"Processed {offset} wikis for namespace {namespace}")
            
            # Save checkpoint periodically
            now = datetime.now()
            if (now - last_checkpoint_time).total_seconds() >= checkpoint_interval:
                save_checkpoint()
            
            # Display progress periodically
            if (now - last_checkpoint_time).total_seconds() >= stats_interval:
                display_progress()
        
        print(f"Completed fetching {total_wikis} wikis for namespace {namespace}")
    except Exception as e:
        print(f"Error in fetch_and_store_wikis: {e}")
    finally:
        if 'conn' in locals() and conn:
            conn.close()

# Main function
def main():
    global current_offset, guides_processed, wikis_processed, categories_processed, media_downloaded, start_time, last_checkpoint_time
    
    print(f"Starting iFixit data fetcher at {datetime.now()}")
    
    # Load checkpoint if exists
    if load_checkpoint():
        # Checkpoint found, current_offset has been updated
        pass
    else:
        # No checkpoint, start from beginning
        current_offset = 0
        guides_processed = 0
        wikis_processed = 0
        categories_processed = 0
        media_downloaded = 0
    
    # Record start time
    start_time = datetime.now()
    last_checkpoint_time = datetime.now()
    
    try:
        # First, fetch and store categories
        print("=== Fetching Categories ===")
        fetch_and_store_categories()
        
        # Next, fetch and store wikis for each namespace
        print("=== Fetching Wikis ===")
        for namespace in ['CATEGORY', 'ITEM', 'INFO']:
            print(f"Fetching wikis for namespace: {namespace}")
            fetch_and_store_wikis(namespace)
        
        # Now fetch guides
        print("=== Fetching Guides ===")
        conn = psycopg2.connect(**db_params)
        
        batch_size = 20  # Number of guides to fetch per API call
        
        while True:
            guides = fetch_guides(limit=batch_size, offset=current_offset)
            
            if not guides or len(guides) == 0:
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
            
        # After guides, fetch some product information
        # This is just a sample of products - we don't know all product codes
        print("=== Fetching Sample Products ===")
        
        # Try to get some product codes from the database
        cursor = conn.cursor()
        cursor.execute("""
            SELECT DISTINCT category 
            FROM guides 
            WHERE category IS NOT NULL AND category != ''
            LIMIT 50
        """)
        
        categories = [row[0] for row in cursor.fetchall()]
        
        # Use these categories to get product suggestions
        for category in categories:
            try:
                suggestions = fetch_suggestions(category)
                
                if suggestions and 'results' in suggestions:
                    for result in suggestions['results']:
                        if 'dataType' in result and result['dataType'] == 'wiki':
                            # This could be a product category
                            wiki_title = result.get('title')
                            
                            # Fetch product info using title as itemcode
                            product_info = fetch_product(wiki_title)
                            
                            if product_info:
                                # Store product info in database
                                store_product_in_db(product_info, conn)
                                
                                # Be nice to the API
                                time.sleep(1)
            except Exception as e:
                print(f"Error fetching product info for category {category}: {e}")
        
        conn.close()
        
    except Exception as e:
        print(f"Error in main process: {e}")
        # Save checkpoint in case of error
        save_checkpoint()
    
    print(f"Completed iFixit data fetcher at {datetime.now()}")
    print(f"Total guides processed: {guides_processed}")
    print(f"Total wikis processed: {wikis_processed}")
    print(f"Total categories processed: {categories_processed}")
    print(f"Total media downloaded: {media_downloaded}")

if __name__ == "__main__":
    main()
