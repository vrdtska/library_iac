<?xml version="1.0" encoding="UTF-8"?>
<xsl:stylesheet version="1.0" xmlns:xsl="http://www.w3.org/1999/XSL/Transform">
    <xsl:output method="html" encoding="UTF-8" doctype-public="-//W3C//DTD HTML 4.01//EN" doctype-system="http://www.w3.org/TR/html4/strict.dtd" indent="yes"/>
    
    <xsl:template match="/">
        <html lang="en">
            <head>
                <meta charset="UTF-8"/>
                <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
                <title>Library Inventory Management System</title>
                <style>
                    * {
                        margin: 0;
                        padding: 0;
                        box-sizing: border-box;
                    }

                    body {
                        font-family: 'Segoe UI', 'Roboto', 'Oxygen', 'Ubuntu', Cantarell, sans-serif;
                        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                        min-height: 100vh;
                        padding: 20px;
                    }

                    .container {
                        max-width: 1400px;
                        margin: 0 auto;
                    }

                    .header {
                        background: rgba(255, 255, 255, 0.98);
                        padding: 40px 30px;
                        border-radius: 15px;
                        margin-bottom: 40px;
                        box-shadow: 0 10px 30px rgba(0, 0, 0, 0.15);
                        text-align: center;
                    }

                    .header h1 {
                        color: #667eea;
                        font-size: 42px;
                        margin-bottom: 10px;
                        font-weight: 700;
                        letter-spacing: -0.5px;
                    }

                    .header p {
                        color: #666;
                        font-size: 16px;
                        margin-top: 10px;
                    }

                    .stats {
                        display: flex;
                        justify-content: center;
                        gap: 40px;
                        margin-top: 25px;
                        flex-wrap: wrap;
                    }

                    .stat-item {
                        text-align: center;
                    }

                    .stat-number {
                        display: block;
                        font-size: 32px;
                        color: #764ba2;
                        font-weight: bold;
                    }

                    .stat-label {
                        color: #999;
                        font-size: 12px;
                        text-transform: uppercase;
                        letter-spacing: 1px;
                        margin-top: 5px;
                    }

                    .books-grid {
                        display: grid;
                        grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
                        gap: 30px;
                        margin-bottom: 40px;
                    }

                    .book-card {
                        background: white;
                        border-radius: 12px;
                        overflow: hidden;
                        box-shadow: 0 8px 20px rgba(0, 0, 0, 0.1);
                        transition: all 0.3s ease;
                        display: flex;
                        flex-direction: column;
                        height: 100%;
                    }

                    .book-card:hover {
                        transform: translateY(-10px);
                        box-shadow: 0 15px 40px rgba(102, 126, 234, 0.3);
                    }

                    .book-header {
                        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                        color: white;
                        padding: 15px;
                        font-size: 12px;
                        font-weight: bold;
                        letter-spacing: 1px;
                        text-transform: uppercase;
                    }

                    .book-image {
                        width: 100%;
                        height: 250px;
                        background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        color: #999;
                        font-size: 14px;
                        overflow: hidden;
                        position: relative;
                    }

                    .book-image img {
                        max-width: 100%;
                        max-height: 100%;
                        object-fit: cover;
                    }

                    .book-image-placeholder {
                        text-align: center;
                        width: 100%;
                    }

                    .book-image-icon {
                        font-size: 48px;
                        margin-bottom: 10px;
                    }

                    .book-content {
                        padding: 20px;
                        flex-grow: 1;
                        display: flex;
                        flex-direction: column;
                    }

                    .book-category {
                        display: inline-block;
                        background: #fff3cd;
                        color: #856404;
                        padding: 5px 10px;
                        border-radius: 20px;
                        font-size: 11px;
                        font-weight: 600;
                        margin-bottom: 10px;
                        width: fit-content;
                    }

                    .book-title {
                        font-size: 18px;
                        font-weight: bold;
                        color: #333;
                        margin-bottom: 8px;
                        line-height: 1.3;
                        min-height: 50px;
                    }

                    .book-authors {
                        color: #667eea;
                        font-size: 13px;
                        font-weight: 600;
                        margin-bottom: 10px;
                    }

                    .book-year {
                        color: #999;
                        font-size: 12px;
                        margin-bottom: 12px;
                    }

                    .book-description {
                        color: #666;
                        font-size: 13px;
                        line-height: 1.5;
                        margin-bottom: 15px;
                        flex-grow: 1;
                    }

                    .book-genres {
                        display: flex;
                        gap: 6px;
                        flex-wrap: wrap;
                        margin-bottom: 15px;
                    }

                    .genre-tag {
                        background: #e8f0ff;
                        color: #667eea;
                        padding: 4px 8px;
                        border-radius: 4px;
                        font-size: 11px;
                        font-weight: 600;
                    }

                    .book-footer {
                        border-top: 1px solid #f0f0f0;
                        padding-top: 15px;
                        display: flex;
                        justify-content: space-between;
                        align-items: center;
                    }

                    .book-price {
                        font-size: 24px;
                        font-weight: bold;
                        color: #27ae60;
                    }

                    .price-currency {
                        font-size: 14px;
                    }

                    .book-stock {
                        display: flex;
                        align-items: center;
                        gap: 8px;
                    }

                    .stock-indicator {
                        width: 12px;
                        height: 12px;
                        border-radius: 50%;
                        display: inline-block;
                    }

                    .stock-high {
                        background: #27ae60;
                    }

                    .stock-medium {
                        background: #f39c12;
                    }

                    .stock-low {
                        background: #e74c3c;
                    }

                    .stock-text {
                        font-size: 13px;
                        color: #666;
                        font-weight: 600;
                    }

                    .book-format {
                        display: inline-block;
                        background: #ffe8d4;
                        color: #cc6600;
                        padding: 5px 10px;
                        border-radius: 4px;
                        font-size: 11px;
                        font-weight: 600;
                        margin-left: auto;
                    }

                    .concepts-section {
                        background: #f9f9f9;
                        padding: 15px;
                        border-radius: 8px;
                        margin-top: 15px;
                    }

                    .concepts-title {
                        font-size: 12px;
                        font-weight: bold;
                        color: #333;
                        text-transform: uppercase;
                        letter-spacing: 0.5px;
                        margin-bottom: 10px;
                    }

                    .concept-item {
                        background: white;
                        padding: 10px;
                        border-radius: 4px;
                        margin-bottom: 8px;
                        border-left: 3px solid #667eea;
                        font-size: 12px;
                    }

                    .concept-name {
                        font-weight: bold;
                        color: #667eea;
                        display: block;
                        margin-bottom: 3px;
                    }

                    .concept-definition {
                        color: #666;
                        font-size: 11px;
                        line-height: 1.4;
                        font-style: italic;
                    }

                    .footer {
                        background: rgba(255, 255, 255, 0.9);
                        padding: 30px;
                        border-radius: 12px;
                        text-align: center;
                        color: #666;
                        font-size: 13px;
                        margin-top: 40px;
                    }

                    .inventory-summary {
                        display: grid;
                        grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                        gap: 20px;
                        margin-bottom: 40px;
                        background: rgba(255, 255, 255, 0.95);
                        padding: 30px;
                        border-radius: 12px;
                        box-shadow: 0 8px 20px rgba(0, 0, 0, 0.1);
                    }

                    .summary-card {
                        text-align: center;
                        padding: 20px;
                        border-radius: 8px;
                        background: linear-gradient(135deg, #667eea15 0%, #764ba215 100%);
                        border: 1px solid #e0e0e0;
                    }

                    .summary-value {
                        font-size: 32px;
                        font-weight: bold;
                        color: #667eea;
                        margin-bottom: 5px;
                    }

                    .summary-label {
                        font-size: 12px;
                        color: #999;
                        text-transform: uppercase;
                        letter-spacing: 0.5px;
                    }

                    @media (max-width: 768px) {
                        .header h1 {
                            font-size: 28px;
                        }

                        .books-grid {
                            grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
                            gap: 20px;
                        }

                        .stats {
                            gap: 20px;
                        }

                        .book-footer {
                            flex-direction: column;
                            gap: 10px;
                            align-items: flex-start;
                        }
                    }

                    @media (max-width: 480px) {
                        body {
                            padding: 10px;
                        }

                        .header {
                            padding: 20px;
                        }

                        .header h1 {
                            font-size: 24px;
                        }

                        .books-grid {
                            grid-template-columns: 1fr;
                        }

                        .inventory-summary {
                            grid-template-columns: 1fr;
                        }
                    }
                </style>
            </head>
            <body>
                <div class="container">
                    <!-- Header -->
                    <div class="header">
                        <h1>📚 Library Inventory Management</h1>
                        <p>Professional Book Catalog & Inventory System</p>
                        <div class="stats">
                            <div class="stat-item">
                                <span class="stat-number"><xsl:value-of select="count(//book)"/></span>
                                <span class="stat-label">Total Books</span>
                            </div>
                            <div class="stat-item">
                                <span class="stat-number"><xsl:value-of select="sum(//stock)"/></span>
                                <span class="stat-label">Items in Stock</span>
                            </div>
                            <div class="stat-item">
                                <span class="stat-number">$<xsl:value-of select="format-number(sum(//price), '0.00')"/></span>
                                <span class="stat-label">Total Value</span>
                            </div>
                        </div>
                    </div>

                    <!-- Books Grid -->
                    <div class="books-grid">
                        <xsl:apply-templates select="//book"/>
                    </div>

                    <!-- Footer -->
                    <div class="footer">
                        <p>Library Inventory System v1.0 | Generated with XSL Transformation | <xsl:value-of select="count(//book)"/> books available</p>
                    </div>
                </div>
            </body>
        </html>
    </xsl:template>

    <!-- Book Card Template -->
    <xsl:template match="book">
        <div class="book-card">
            <div class="book-header">
                ISBN: <xsl:value-of select="@isbn"/>
            </div>
            
            <div class="book-image">
                <div class="book-image-placeholder">
                    <div class="book-image-icon">📖</div>
                    <xsl:choose>
                        <xsl:when test="images/image[@isCover='true']">
                            <div style="font-size: 11px; margin-top: 10px;">Cover Image: <xsl:value-of select="images/image[@isCover='true']/@altText"/></div>
                        </xsl:when>
                        <xsl:otherwise>
                            <div style="font-size: 11px; margin-top: 10px;">Book Cover</div>
                        </xsl:otherwise>
                    </xsl:choose>
                </div>
            </div>

            <div class="book-content">
                <div class="book-category"><xsl:value-of select="category"/></div>
                
                <div class="book-title"><xsl:value-of select="title"/></div>
                
                <div class="book-authors">
                    <xsl:for-each select="authors/author">
                        <xsl:if test="position() > 1">, </xsl:if>
                        <xsl:value-of select="."/>
                    </xsl:for-each>
                </div>

                <div class="book-year">Published: <xsl:value-of select="publicationYear"/></div>

                <div class="book-genres">
                    <xsl:for-each select="genres/genre">
                        <span class="genre-tag"><xsl:value-of select="."/></span>
                    </xsl:for-each>
                </div>

                <div class="book-description">
                    <xsl:value-of select="description"/>
                </div>

                <div class="concepts-section">
                    <div class="concepts-title">Key Concepts</div>
                    <xsl:for-each select="concepts/concept[position() &lt;= 2]">
                        <div class="concept-item">
                            <span class="concept-name"><xsl:value-of select="@name"/></span>
                            <span class="concept-definition"><xsl:value-of select="@definition"/></span>
                        </div>
                    </xsl:for-each>
                </div>

                <div class="book-footer">
                    <div>
                        <div class="book-price">
                            <span class="price-currency"><xsl:value-of select="price/@currency"/></span> <xsl:value-of select="price"/>
                        </div>
                    </div>
                    <div class="book-stock">
                        <span class="stock-indicator">
                            <xsl:choose>
                                <xsl:when test="stock >= 50">
                                    <xsl:attribute name="class">stock-indicator stock-high</xsl:attribute>
                                </xsl:when>
                                <xsl:when test="stock >= 20">
                                    <xsl:attribute name="class">stock-indicator stock-medium</xsl:attribute>
                                </xsl:when>
                                <xsl:otherwise>
                                    <xsl:attribute name="class">stock-indicator stock-low</xsl:attribute>
                                </xsl:otherwise>
                            </xsl:choose>
                        </span>
                        <span class="stock-text"><xsl:value-of select="stock"/> units</span>
                    </div>
                    <div class="book-format"><xsl:value-of select="format"/></div>
                </div>
            </div>
        </div>
    </xsl:template>

</xsl:stylesheet>
