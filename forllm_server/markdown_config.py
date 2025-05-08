from markdown_it import MarkdownIt
from pygments import highlight
from pygments.lexers import get_lexer_by_name, TextLexer
from pygments.formatters import HtmlFormatter

# Custom highlight function using Pygments
def pygments_highlight(code, lang, attrs):
    try:
        # Use get_lexer_by_name if language is specified, otherwise TextLexer
        lexer = get_lexer_by_name(lang) if lang else TextLexer()
    except Exception:
        # Fallback to TextLexer if the language is unknown
        lexer = TextLexer()
    # Use the default HTML formatter
    formatter = HtmlFormatter()
    # Return the highlighted code HTML
    return highlight(code, lexer, formatter)

# Configure markdown-it with the custom highlighter
md = (
    MarkdownIt(
        'commonmark',
        {
            'breaks': True,     # Convert '\n' in paragraphs into <br>
            'html': False,      # Disable HTML tags in source
            'linkify': True,    # Autoconvert URL-like text to links
            'highlight': pygments_highlight # Use our Pygments function HERE, inside options
        }
    )
    .enable('table') # Enable GFM tables
    # Add other plugins or rules as needed
)