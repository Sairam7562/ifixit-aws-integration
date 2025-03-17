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
            "/api/guides/<guide_id>"
        ]
    })

@app.route('/api/guides', methods=['GET'])
def get_guides():
    try:
        # Parse query parameters
        limit = min(int(request.args.get('limit', 20)), 100)  # Max 100 records
        offset = int(request.args.get('offset', 0))
        category = request.args.get('category')
        
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
                   m.s3_path as image_path
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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
