{
    'name': 'Product HSN and Tax Audit History',
    'version': '18.0.1.0.0',
    'category': 'Product',
    'depends': ['stock', 'sale_management', 'purchase', 'account'],
    'data': [
        'security/ir.model.access.csv',
        'views/product_template_views.xml',
    ],
    'installable': True,
    'application': False,
}