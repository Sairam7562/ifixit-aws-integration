from flask import Flask, jsonify, request
from flask_cors import CORS
import psycopg2
import psycopg2.extras
import os
from dotenv import load_dotenv
import boto3
from botocore.client import Config

load_dotenv()

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# Database connection parameters
db_params = {
    'dbname': os.getenv('DB_NAME'),
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
    'host': os.getenv('DB_HOST'),
    'port': os.getenv('DB_PORT', '5432')
}

# S3 configuration
s3_client = boto3.client(
    's3',
    config=Config(signature_version='s3v4')
)
MEDIA_BUCKET = os.getenv('MEDIA_BUCKET')

# Helper function to get DB connection
def get_db_connection():
    conn = psycopg2.connect(**db_params)
    conn.cursor_factory = psycopg2.extras.RealDictCursor
    return conn

@app.route('/')
def home():
    return jsonify({
        "status": "success",
        "message": "iFixit API Server is running",
        "endpoints": [
            "/api/guides",
            "/api/guides/<guide_id>",
            "/api/categories",
            "/api/categories/<title>",
            "/api/products",
            "/api/products/<itemcode>",
            "/api/tags"
        ]
    })

@app.route('/api/guides', methods=['GET'])
def get_guides():
    try:
        # Parse query parameters
        limit = min(int(request.args.get('limit', 20)), 100)  # Max 100 records
        offset = int(request.args.get('offset', 0))
        category = request.args.get('category')
        tag = request.args.get('tag')
        search = request.args.get('search')
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Build query
        query = """
            SELECT g.id, g.external_id, g.title, g.subject, 
                   g.type, g.difficulty, g.category,
                   m.s3_path as image_path
            FROM guides g
            LEFT JOIN media m ON g.id = m.guide_id AND m.step_id IS NULL
        """
        
        params = []
        where_clauses = []
        
        if category:
            where_clauses.append("g.category = %s")
            params.append(category)
        
        if tag:
            query += " JOIN guide_tags gt ON g.id = gt.guide_id JOIN tags t ON gt.tag_id = t.id"
            where_clauses.append("t.name = %s")
            params.append(tag)
        
        if search:
            where_clauses.append("g.title ILIKE %s")
            search_param = f"%{search}%"
            params.append(search_param)
        
        if where_clauses:
            query += " WHERE " + " AND ".join(where_clauses)
        
        query += " ORDER BY g.id LIMIT %s OFFSET %s"
        params.extend([limit, offset])
        
        cursor.execute(query, params)
        guides = cursor.fetchall()
        
        # Generate presigned URLs for images
        for guide in guides:
            if guide['image_path']:
                try:
                    guide['image_url'] = s3_client.generate_presigned_url(
                        'get_object',
                        Params={'Bucket': MEDIA_BUCKET, 'Key': guide['image_path']},
                        ExpiresIn=3600
                    )
                except Exception as e:
                    print(f"Error generating presigned URL: {e}")
                    guide['image_url'] = None
        
        return jsonify({
            "status": "success",
            "count": len(guides),
            "guides": guides
        })
    except Exception as e:
        print(f"Error in get_guides: {e}")
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500
    finally:
        if 'cursor' in locals() and cursor:
            cursor.close()
        if 'conn' in locals() and conn:
            conn.close()

@app.route('/api/guides/<guide_id>', methods=['GET'])
def get_guide(guide_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get guide details
        cursor.execute("""
            SELECT g.id, g.external_id, g.title, g.subject, 
                   g.type, g.difficulty, g.category,
                   m.s3_path as image_path, g.raw_data
            FROM guides g
            LEFT JOIN media m ON g.id = m.guide_id AND m.step_id IS NULL
            WHERE g.external_id = %s
        """, (guide_id,))
        
        guide = cursor.fetchone()
        if not guide:
            return jsonify({
                "status": "error",
                "message": "Guide not found"
            }), 404
        
        # Get steps with raw_data
        cursor.execute("""
            SELECT s.id, s.external_id, s.orderby, s.title, s.raw_data
            FROM steps s
            WHERE s.guide_id = %s
            ORDER BY s.orderby
        """, (guide['id'],))
        
        steps = cursor.fetchall()
        guide['steps'] = steps
        
        # Get media for each step
        for step in steps:
            cursor.execute("""
                SELECT id, media_type, external_id, s3_path
                FROM media
                WHERE guide_id = %s AND step_id = %s
            """, (guide['id'], step['id']))
            
            media = cursor.fetchall()
            step['media'] = media
            
            # Generate presigned URLs for media
            for item in media:
                if item['s3_path']:
                    try:
                        item['url'] = s3_client.generate_presigned_url(
                            'get_object',
                            Params={'Bucket': MEDIA_BUCKET, 'Key': item['s3_path']},
                            ExpiresIn=3600
                        )
                    except Exception as e:
                        print(f"Error generating presigned URL: {e}")
                        item['url'] = None
        
        # Get tags
        cursor.execute("""
            SELECT t.id, t.name
            FROM tags t
            JOIN guide_tags gt ON t.id = gt.tag_id
            WHERE gt.guide_id = %s
        """, (guide['id'],))
        
        tags = cursor.fetchall()
        guide['tags'] = tags
        
        # Generate presigned URL for guide image
        if guide['image_path']:
            try:
                guide['image_url'] = s3_client.generate_presigned_url(
                    'get_object',
                    Params={'Bucket': MEDIA_BUCKET, 'Key': guide['image_path']},
                    ExpiresIn=3600
                )
            except Exception as e:
                print(f"Error generating presigned URL: {e}")
                guide['image_url'] = None
        
        return jsonify({
            "status": "success",
            "guide": guide
        })
    except Exception as e:
        print(f"Error in get_guide: {e}")
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500
    finally:
        if 'cursor' in locals() and cursor:
            cursor.close()
        if 'conn' in locals() and conn:
            conn.close()

@app.route('/api/categories', methods=['GET'])
def get_categories():
    try:
        # Parse query parameters
        parent_id = request.args.get('parent_id')
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Build query
        query = """
            SELECT id, title, display_title, category_path, parent_id, wikiid
            FROM categories
        """
        
        params = []
        where_clauses = []
        
        if parent_id:
            where_clauses.append("parent_id = %s")
            params.append(parent_id)
        else:
            # If no parent_id is specified, return top-level categories
            where_clauses.append("parent_id IS NULL")
        
        if where_clauses:
            query += " WHERE " + " AND ".join(where_clauses)
        
        query += " ORDER BY title"
        
        cursor.execute(query, params)
        categories = cursor.fetchall()
        
        return jsonify({
            "status": "success",
            "count": len(categories),
            "categories": categories
        })
    except Exception as e:
        print(f"Error in get_categories: {e}")
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500
    finally:
        if 'cursor' in locals() and cursor:
            cursor.close()
        if 'conn' in locals() and conn:
            conn.close()

@app.route('/api/categories/<path:title>', methods=['GET'])
def get_category(title):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get category details
        cursor.execute("""
            SELECT id, title, display_title, category_path, parent_id, wikiid, namespace, raw_data
            FROM categories
            WHERE title = %s OR display_title = %s
        """, (title, title))
        
        category = cursor.fetchone()
        if not category:
            return jsonify({
                "status": "error",
                "message": "Category not found"
            }), 404
        
        # Get subcategories
        cursor.execute("""
            SELECT id, title, display_title, category_path, parent_id, wikiid
            FROM categories
            WHERE parent_id = %s
            ORDER BY title
        """, (category['id'],))
        
        subcategories = cursor.fetchall()
        category['subcategories'] = subcategories
        
        # Get guides in this category
        cursor.execute("""
            SELECT id, external_id, title, subject, type, difficulty
            FROM guides
            WHERE category = %s
            ORDER BY title
            LIMIT 50
        """, (category['title'],))
        
        guides = cursor.fetchall()
        category['guides'] = guides
        
        return jsonify({
            "status": "success",
            "category": category
        })
    except Exception as e:
        print(f"Error in get_category: {e}")
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500
    finally:
        if 'cursor' in locals() and cursor:
            cursor.close()
        if 'conn' in locals() and conn:
            conn.close()

@app.route('/api/products', methods=['GET'])
def get_products():
    try:
        # Parse query parameters
        limit = min(int(request.args.get('limit', 20)), 100)  # Max 100 records
        offset = int(request.args.get('offset', 0))
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get product list
        cursor.execute("""
            SELECT id, itemcode, productcode, title
            FROM products
            ORDER BY title
            LIMIT %s OFFSET %s
        """, (limit, offset))
        
        products = cursor.fetchall()
        
        return jsonify({
            "status": "success",
            "count": len(products),
            "products": products
        })
    except Exception as e:
        print(f"Error in get_products: {e}")
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500
    finally:
        if 'cursor' in locals() and cursor:
            cursor.close()
        if 'conn' in locals() and conn:
            conn.close()

@app.route('/api/products/<itemcode>', methods=['GET'])
def get_product(itemcode):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get product details
        cursor.execute("""
            SELECT id, itemcode, productcode, title, raw_data
            FROM products
            WHERE itemcode = %s
        """, (itemcode,))
        
        product = cursor.fetchone()
        if not product:
            return jsonify({
                "status": "error",
                "message": "Product not found"
            }), 404
        
        # Get related guides
        cursor.execute("""
            SELECT g.id, g.external_id, g.title, g.subject, g.type, g.difficulty
            FROM guides g
            JOIN product_guides pg ON g.id = pg.guide_id
            WHERE pg.product_id = %s
            ORDER BY g.title
        """, (product['id'],))
        
        guides = cursor.fetchall()
        product['guides'] = guides
        
        # Get related wikis
        cursor.execute("""
            SELECT pw.wiki_id, c.title, c.display_title
            FROM product_wikis pw
            LEFT JOIN categories c ON pw.wiki_id = c.wikiid
            WHERE pw.product_id = %s
        """, (product['id'],))
        
        wikis = cursor.fetchall()
        product['wikis'] = wikis
        
        return jsonify({
            "status": "success",
            "product": product
        })
    except Exception as e:
        print(f"Error in get_product: {e}")
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500
    finally:
        if 'cursor' in locals() and cursor:
            cursor.close()
        if 'conn' in locals() and conn:
            conn.close()

@app.route('/api/tags', methods=['GET'])
def get_tags():
    try:
        # Parse query parameters
        limit = min(int(request.args.get('limit', 100)), 500)  # Max 500 records
        offset = int(request.args.get('offset', 0))
        sort_by = request.args.get('sort', 'name')  # Sort by name or popularity
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Build query based on sort parameter
        if sort_by == 'popularity':
            query = """
                SELECT t.id, t.name, COUNT(gt.guide_id) as guide_count
                FROM tags t
                LEFT JOIN guide_tags gt ON t.id = gt.tag_id
                GROUP BY t.id, t.name
                ORDER BY guide_count DESC, t.name
                LIMIT %s OFFSET %s
            """
        else:  # Default sort by name
            query = """
                SELECT t.id, t.name, COUNT(gt.guide_id) as guide_count
                FROM tags t
                LEFT JOIN guide_tags gt ON t.id = gt.tag_id
                GROUP BY t.id, t.name
                ORDER BY t.name
                LIMIT %s OFFSET %s
            """
        
        cursor.execute(query, (limit, offset))
        tags = cursor.fetchall()
        
        return jsonify({
            "status": "success",
            "count": len(tags),
            "tags": tags
        })
    except Exception as e:
        print(f"Error in get_tags: {e}")
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500
    finally:
        if 'cursor' in locals() and cursor:
            cursor.close()
        if 'conn' in locals() and conn:
            conn.close()

@app.route('/api/search', methods=['GET'])
def search():
    try:
        # Parse query parameters
        query = request.args.get('q', '')
        limit = min(int(request.args.get('limit', 20)), 100)  # Max 100 records
        
        if not query:
            return jsonify({
                "status": "error",
                "message": "Query parameter 'q' is required"
            }), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Search guides
        cursor.execute("""
            SELECT 'guide' as type, id, external_id as identifier, title, '' as summary
            FROM guides
            WHERE title ILIKE %s
            LIMIT %s
        """, (f"%{query}%", limit))
        
        guide_results = cursor.fetchall()
        
        # Search categories
        cursor.execute("""
            SELECT 'category' as type, id, title as identifier, display_title as title, '' as summary
            FROM categories
            WHERE title ILIKE %s OR display_title ILIKE %s
            LIMIT %s
        """, (f"%{query}%", f"%{query}%", limit))
        
        category_results = cursor.fetchall()
        
        # Search products
        cursor.execute("""
            SELECT 'product' as type, id, itemcode as identifier, title, '' as summary
            FROM products
            WHERE title ILIKE %s OR itemcode ILIKE %s
            LIMIT %s
        """, (f"%{query}%", f"%{query}%", limit))
        
        product_results = cursor.fetchall()
        
        # Search tags
        cursor.execute("""
            SELECT 'tag' as type, id, name as identifier, name as title, '' as summary
            FROM tags
            WHERE name ILIKE %s
            LIMIT %s
        """, (f"%{query}%", limit))
        
        tag_results = cursor.fetchall()
        
        # Combine results
        all_results = guide_results + category_results + product_results + tag_results
        
        # Sort results by relevance (simple implementation: exact matches first, then by title)
        all_results.sort(key=lambda x: (
            0 if x['title'] and x['title'].lower() == query.lower() else 1,
            0 if x['identifier'] and x['identifier'].lower() == query.lower() else 1,
            x['title'] if x['title'] else ''
        ))
        
        return jsonify({
            "status": "success",
            "count": len(all_results),
            "results": all_results[:limit]  # Limit total results
        })
    except Exception as e:
        print(f"Error in search: {e}")
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500
    finally:
        if 'cursor' in locals() and cursor:
            cursor.close()
        if 'conn' in locals() and conn:
            conn.close()

@app.route('/api/stats', methods=['GET'])
def stats():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Collect various statistics
        stats = {}
        
        # Count guides
        cursor.execute("SELECT COUNT(*) FROM guides")
        stats['guides_count'] = cursor.fetchone()['count']
        
        # Count categories
        cursor.execute("SELECT COUNT(*) FROM categories")
        stats['categories_count'] = cursor.fetchone()['count']
        
        # Count tags
        cursor.execute("SELECT COUNT(*) FROM tags")
        stats['tags_count'] = cursor.fetchone()['count']
        
        # Count products
        cursor.execute("SELECT COUNT(*) FROM products")
        stats['products_count'] = cursor.fetchone()['count']
        
        # Count media
        cursor.execute("SELECT COUNT(*) FROM media")
        stats['media_count'] = cursor.fetchone()['count']
        
        # Get top categories by guide count
        cursor.execute("""
            SELECT c.title, c.display_title, COUNT(g.id) as guide_count
            FROM categories c
            JOIN guides g ON c.title = g.category
            GROUP BY c.id, c.title, c.display_title
            ORDER BY guide_count DESC
            LIMIT 10
        """)
        stats['top_categories'] = cursor.fetchall()
        
        # Get top tags by guide count
        cursor.execute("""
            SELECT t.name, COUNT(gt.guide_id) as guide_count
            FROM tags t
            JOIN guide_tags gt ON t.id = gt.tag_id
            GROUP BY t.id, t.name
            ORDER BY guide_count DESC
            LIMIT 10
        """)
        stats['top_tags'] = cursor.fetchall()
        
        return jsonify({
            "status": "success",
            "stats": stats
        })
    except Exception as e:
        print(f"Error in stats: {e}")
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500
    finally:
        if 'cursor' in locals() and cursor:
            cursor.close()
        if 'conn' in locals() and conn:
            conn.close()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
