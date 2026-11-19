AUTHOR = 'Heritage Boat Association Archive'
SITENAME = 'Heritage Boat Association Archive'
SITEURL = ''

PATH = 'content'

ARTICLE_PATHS = ['articles']
PAGE_PATHS = ['pages', 'archive']

TIMEZONE = 'Europe/Dublin'

DEFAULT_LANG = 'en'

# Feed generation is usually not desired when developing
FEED_ALL_ATOM = None
CATEGORY_FEED_ATOM = None
TRANSLATION_FEED_ATOM = None
AUTHOR_FEED_ATOM = None
AUTHOR_FEED_RSS = None

# Navigation
DISPLAY_PAGES_ON_MENU = False
MENUITEMS = (
    ('Home', '/'),
    ('About', '/pages/about.html'),
    ('Vessels', '/archive/vessels/index.html'),
    ('Archive', '/pages/archive.html'),
    ('News & Articles', '/category/news.html'),
)

# Theme
THEME = 'theme'

# Blogroll
LINKS = ()

# Social widget
SOCIAL = ()

DEFAULT_PAGINATION = False

# Static paths
STATIC_PATHS = ['images', 'audio', 'js', 'data', 'extra/CNAME']
EXTRA_PATH_METADATA = {'extra/CNAME': {'path': 'CNAME'}}
