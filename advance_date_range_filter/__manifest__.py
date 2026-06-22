{
    'name': 'Advanced Date Range Filter',
    'version': '18.0.1.0.0',
    'category': 'Tools',
    'author': 'iprogrammer solution pvt ltd',
    'depends': ['base', 'web'],
    'data': [
        'security/ir.model.access.csv',
        'views/date_filter_config_views.xml',
        'views/menu_items.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'advance_date_range_filter/static/src/css/date_range_filter.css',
            'advance_date_range_filter/static/src/js/date_range_filter.js',
            'advance_date_range_filter/static/src/xml/date_range_filter.xml',
        ],
    },
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}