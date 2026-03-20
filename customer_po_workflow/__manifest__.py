{
    'name': 'Customer PO Workflow',
    'version': '1.0',
    'category': 'Sales',
    'summary': 'Automates Customer PO → SO → Production → Invoice → Stock',
    'depends': ['sale_management', 'stock', 'mrp', 'account'],
    'data': [
        'security/ir.model.access.csv',
        'views/customer_po.xml',
        'views/sale_order_mo.xml',
    ],
    'installable': True,
    'application': False,
}
