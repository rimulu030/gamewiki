"""
Markdown to HTML converter for game wiki tooltip.
"""

import re
import logging

# Import markdown support
try:
    import markdown
    MARKDOWN_AVAILABLE = True
    
    # Disable markdown library debug log output to avoid excessive debug information
    markdown_logger = logging.getLogger('markdown')
    markdown_logger.setLevel(logging.WARNING)
    
except ImportError:
    print("Warning: markdown library not available. Markdown content will be displayed as plain text.")
    MARKDOWN_AVAILABLE = False


def convert_markdown_to_html(text: str) -> str:
    """
    Convert markdown text to HTML while preserving existing HTML tags
    
    Args:
        text: Markdown text or mixed HTML content
        
    Returns:
        Converted HTML text
    """
    if not text:
        return text
        
    try:
        # Check if HTML tags are present (especially in video source sections)
        has_html_tags = bool(re.search(r'<[^>]+>', text, re.MULTILINE | re.DOTALL))
        
        if has_html_tags:
            # Check if it's mixed content (Markdown + HTML video sources)
            # Improvement: Use more flexible video source recognition
            video_source_patterns = [
                r'---\s*\n\s*<small>',  # Original pattern
                r'📺\s*\*\*info source：\*\*',  # Video source title pattern  
                r'\n\n<small>.*?来源.*?</small>',  # Generic source pattern
                r'\n\n---\n\s*<small>',  # Add more flexible separator pattern
            ]
            
            video_source_start = -1
            used_pattern = None
            
            for pattern in video_source_patterns:
                match = re.search(pattern, text, re.MULTILINE | re.DOTALL)
                if match:
                    video_source_start = match.start()
                    used_pattern = pattern
                    break
            
            if video_source_start != -1:
                # Separate Markdown and HTML parts
                markdown_content = text[:video_source_start].strip()
                html_content = text[video_source_start:].strip()
                
                # Process Markdown part
                processed_markdown = ""
                if markdown_content:
                    if MARKDOWN_AVAILABLE:
                        # Use markdown library
                        available_extensions = []
                        try:
                            import markdown.extensions.extra
                            available_extensions.append('extra')
                        except ImportError:
                            pass
                        try:
                            import markdown.extensions.nl2br
                            available_extensions.append('nl2br')
                        except ImportError:
                            pass
                        
                        if available_extensions:
                            md = markdown.Markdown(extensions=available_extensions)
                        else:
                            md = markdown.Markdown()
                        
                        processed_markdown = md.convert(markdown_content)
                    else:
                        # When markdown library is not available, process basic formats
                        processed_markdown = markdown_content.replace('\n', '<br/>')
                        processed_markdown = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', processed_markdown)
                        processed_markdown = re.sub(r'\*(.*?)\*', r'<em>\1</em>', processed_markdown)
                        processed_markdown = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', processed_markdown)
                
                # Process HTML part, ensure correct formatting
                processed_html = html_content
                if html_content:
                    # Clean up possible markdown separators
                    processed_html = re.sub(r'^---\s*\n\s*', '', processed_html, flags=re.MULTILINE)
                    processed_html = processed_html.strip()
                    
                    # Process markdown links in video sources
                    processed_html = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', processed_html)
                
                # Combine processed content
                combined_content = processed_markdown
                if processed_html:
                    # Add appropriate spacing
                    if combined_content and not combined_content.endswith('<br/>'):
                        combined_content += '<br/><br/>'
                    combined_content += processed_html
                
                # Apply style wrapper
                styled_html = f"""
                <div style="
                    font-family: 'Segoe UI', 'Microsoft YaHei', Arial, sans-serif;
                    line-height: 1.6;
                    color: #333;
                    max-width: 100%;
                    word-wrap: break-word;
                ">
                    {combined_content}
                </div>
                """
                return styled_html
            else:
                # Pure HTML content, but still need to process markdown links
                processed_text = text
                # Process markdown links
                processed_text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', processed_text)
                
                styled_html = f"""
                <div style="
                    font-family: 'Segoe UI', 'Microsoft YaHei', Arial, sans-serif;
                    line-height: 1.6;
                    color: #333;
                    max-width: 100%;
                    word-wrap: break-word;
                ">
                    {processed_text}
                </div>
                """
                return styled_html
        
        # If no HTML tags, perform regular markdown processing
        if not MARKDOWN_AVAILABLE:
            # When markdown library is not available, at least process some basic formats
            html = text.replace('\n', '<br/>')
            # Process bold
            html = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', html)
            # Process italic
            html = re.sub(r'\*(.*?)\*', r'<em>\1</em>', html)
            # Process links
            html = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', html)
        else:
            # Use markdown library
            # Configure markdown converter, use basic extensions (avoid dependencies that may not exist)
            available_extensions = []
            
            # Try to add available extensions
            try:
                import markdown.extensions.extra
                available_extensions.append('extra')
            except ImportError:
                pass
                
            try:
                import markdown.extensions.nl2br
                available_extensions.append('nl2br')
            except ImportError:
                pass
                
            # If no extensions available, use basic configuration
            if available_extensions:
                md = markdown.Markdown(extensions=available_extensions)
            else:
                md = markdown.Markdown()
            
            # Convert markdown to HTML
            html = md.convert(text)
        
        # Add some basic styles to make HTML display better
        styled_html = f"""
        <div style="
            font-family: 'Segoe UI', 'Microsoft YaHei', Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 100%;
            word-wrap: break-word;
        ">
            {html}
        </div>
        """
        
        return styled_html
        
    except Exception as e:
        # Only output error information when conversion fails
        print(f"❌ [RENDER-ERROR] Markdown conversion failed: {e}")
        return text