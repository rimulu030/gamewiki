from PyQt6.QtGui import (
    QPainter, QColor, QIcon, QPixmap
)

def load_svg_icon(svg_path, color="#666666", size=16):
    """Load SVG icon and set color"""
    try:
        import os
        from PyQt6.QtSvg import QSvgRenderer
        from PyQt6.QtCore import QByteArray

        # Check if file exists
        if not os.path.exists(svg_path):
            print(f"SVG file not found: {svg_path}")
            return QIcon()

        # Read SVG file
        with open(svg_path, 'r', encoding='utf-8') as f:
            svg_content = f.read()

        # Replace color
        svg_content = svg_content.replace('stroke="#000000"', f'stroke="{color}"')
        svg_content = svg_content.replace('fill="#000000"', f'fill="{color}"')

        # Create icon
        icon = QIcon()
        renderer = QSvgRenderer(QByteArray(svg_content.encode()))

        # Create pixmaps for different sizes
        for s in [size, size * 2]:  # Support high DPI
            pixmap = QPixmap(s, s)
            pixmap.fill(QColor(0, 0, 0, 0))  # Transparent background
            painter = QPainter(pixmap)
            renderer.render(painter)
            painter.end()
            icon.addPixmap(pixmap)

        return icon
    except Exception as e:
        print(f"Failed to load SVG icon: {e}")
        return QIcon()