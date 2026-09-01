"""
Micro-servidor web para la librería en línea
Sirve archivos XML y CSS con una interfaz web
"""

from flask import Flask, render_template_string, send_from_directory, jsonify
import os
from pathlib import Path
import xml.etree.ElementTree as ET

app = Flask(__name__, static_folder='.', static_url_path='')

# Detectar directorio actual
BASE_DIR = Path(__file__).parent.resolve()

# Template HTML para la página de inicio
HOME_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Library Management System</title>
    <link rel="stylesheet" href="/styles.css">
    <style>
        body {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            min-height: 100vh;
            padding: 20px;
        }
        .navbar {
            background: rgba(255, 255, 255, 0.95);
            padding: 20px;
            border-radius: 12px;
            margin-bottom: 30px;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
            display: flex;
            justify-content: space-between;
            align-items: center;
            max-width: 1200px;
            margin-left: auto;
            margin-right: auto;
        }
        .navbar h1 {
            color: #667eea;
            margin: 0;
            font-size: 28px;
        }
        .nav-links {
            display: flex;
            gap: 20px;
        }
        .nav-links a {
            color: #333;
            text-decoration: none;
            font-weight: 600;
            transition: color 0.3s;
            padding: 8px 12px;
            border-radius: 6px;
        }
        .nav-links a:hover {
            color: #667eea;
            background: #f0f0f0;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
        }
        .info-card {
            background: white;
            padding: 20px;
            border-radius: 12px;
            margin-bottom: 20px;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
        }
        .info-card h2 {
            color: #667eea;
            margin-top: 0;
        }
        .endpoints {
            background: #f9f9f9;
            padding: 15px;
            border-radius: 8px;
            border-left: 4px solid #667eea;
        }
        .endpoint {
            margin: 12px 0;
            font-family: monospace;
            padding: 8px;
            background: white;
            border-radius: 4px;
        }
        .endpoint strong {
            color: #667eea;
        }
        .status {
            display: inline-block;
            background: #28a745;
            color: white;
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 12px;
            margin-left: 10px;
        }
    </style>
</head>
<body>
    <div class="navbar">
        <h1>📚 Library Management System</h1>
        <div class="nav-links">
            <a href="/">Home</a>
            <a href="/library.xml">XML</a>
            <a href="/api/books">API</a>
        </div>
    </div>

    <div class="container">
        <div class="info-card">
            <h2>Welcome to the Library Micro-Server <span class="status">RUNNING</span></h2>
            <p>
                This micro-server provides access to your library's XML data and API endpoints.
                You can view the raw XML file or use the JSON API to interact with the library data.
            </p>
        </div>

        <div class="info-card">
            <h2>Available Endpoints</h2>
            <div class="endpoints">
                <div class="endpoint">
                    <strong>GET /</strong> - This home page
                </div>
                <div class="endpoint">
                    <strong>GET /library.xml</strong> - Raw XML file with stylesheet
                </div>
                <div class="endpoint">
                    <strong>GET /styles.css</strong> - CSS stylesheet
                </div>
                <div class="endpoint">
                    <strong>GET /api/books</strong> - List all books (JSON)
                </div>
                <div class="endpoint">
                    <strong>GET /api/books/&lt;isbn&gt;</strong> - Get book by ISBN (JSON)
                </div>
                <div class="endpoint">
                    <strong>GET /api/status</strong> - Server status information
                </div>
            </div>
        </div>

        <div class="info-card">
            <h2>Quick Links</h2>
            <ul>
                <li><a href="/library.xml" style="color: #667eea; text-decoration: underline;">View Library XML</a></li>
                <li><a href="/api/books" style="color: #667eea; text-decoration: underline;">View Books JSON API</a></li>
                <li><a href="/api/status" style="color: #667eea; text-decoration: underline;">Server Status</a></li>
            </ul>
        </div>

        <div class="info-card">
            <h2>Server Information</h2>
            <p><strong>Location:</strong> {{ location }}</p>
            <p><strong>Files available:</strong> {{ files }}</p>
            <p><strong>Running on:</strong> http://localhost:5000</p>
        </div>
    </div>
</body>
</html>
"""

def parse_library_xml():
    """Parse the library.xml file and extract book data"""
    xml_path = BASE_DIR / 'library.xml'
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
        books = []
        
        for book in root.findall('book'):
            isbn = book.get('isbn', 'N/A')
            title = book.findtext('title', 'N/A')
            authors = [author.text for author in book.findall('.//author')]
            year = book.findtext('publicationYear', 'N/A')
            genres = [genre.text for genre in book.findall('.//genre')]
            price = book.findtext('price', 'N/A')
            stock = book.findtext('stock', 'N/A')
            format_type = book.findtext('format', 'N/A')
            category = book.findtext('category', 'N/A')
            description = book.findtext('description', 'N/A')
            
            concepts = []
            for concept in book.findall('.//concept'):
                concepts.append({
                    'name': concept.get('name', 'N/A'),
                    'definition': concept.get('definition', 'N/A')
                })
            
            books.append({
                'isbn': isbn,
                'title': title,
                'authors': authors,
                'publicationYear': year,
                'genres': genres,
                'price': price,
                'stock': stock,
                'format': format_type,
                'category': category,
                'description': description,
                'concepts': concepts
            })
        
        return books
    except Exception as e:
        return []

@app.route('/')
def home():
    """Home page with server information"""
    files = ', '.join([f.name for f in BASE_DIR.glob('*') if f.is_file()])
    return render_template_string(
        HOME_TEMPLATE,
        location=str(BASE_DIR),
        files=files
    )

@app.route('/library.xml')
def serve_xml():
    """Serve the library.xml file"""
    return send_from_directory(str(BASE_DIR), 'library.xml', mimetype='application/xml')

@app.route('/styles.css')
def serve_css():
    """Serve the styles.css file"""
    return send_from_directory(str(BASE_DIR), 'styles.css', mimetype='text/css')

@app.route('/api/books')
def api_books():
    """API endpoint: Get all books as JSON"""
    books = parse_library_xml()
    return jsonify({
        'status': 'success',
        'count': len(books),
        'books': books
    })

@app.route('/api/books/<isbn>')
def api_book_detail(isbn):
    """API endpoint: Get specific book by ISBN"""
    books = parse_library_xml()
    book = next((b for b in books if b['isbn'] == isbn), None)
    
    if book:
        return jsonify({
            'status': 'success',
            'book': book
        })
    else:
        return jsonify({
            'status': 'error',
            'message': f'Book with ISBN {isbn} not found'
        }), 404

@app.route('/api/status')
def api_status():
    """API endpoint: Server status"""
    books = parse_library_xml()
    return jsonify({
        'status': 'running',
        'server_location': str(BASE_DIR),
        'total_books': len(books),
        'files': {
            'xml': 'library.xml',
            'css': 'styles.css'
        }
    })

@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors"""
    return jsonify({
        'status': 'error',
        'message': 'Endpoint not found',
        'available_endpoints': [
            '/',
            '/library.xml',
            '/styles.css',
            '/api/books',
            '/api/books/<isbn>',
            '/api/status'
        ]
    }), 404

if __name__ == '__main__':
    print("=" * 60)
    print("📚 Library Micro-Server")
    print("=" * 60)
    print(f"Server location: {BASE_DIR}")
    print(f"Running on: http://localhost:5000")
    print("\nAvailable endpoints:")
    print("  GET /                    - Home page")
    print("  GET /library.xml         - XML file")
    print("  GET /styles.css          - CSS file")
    print("  GET /api/books           - All books (JSON)")
    print("  GET /api/books/<isbn>    - Book by ISBN (JSON)")
    print("  GET /api/status          - Server status")
    print("\nPress CTRL+C to stop the server")
    print("=" * 60)
    print()
    
    app.run(debug=True, host='0.0.0.0', port=5000)
