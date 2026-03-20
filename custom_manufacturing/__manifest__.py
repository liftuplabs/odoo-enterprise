# -*- coding: utf-8 -*-
{
    'name': "custom_manufacturing",

    'summary': "Custom manufacturing Module",

    'description': """
Long description of module's purpose
    """,

    'author': "My Company",
    'website': "https://www.yourcompany.com",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/15.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Uncategorized',
    'version': '0.1',

    # any module necessary for this one to work correctly
    'depends': ['mrp','maintenance','stock'],

    # always loaded
    'data': [
        'security/ir.model.access.csv',
        'data/production_order_seq.xml',
        'views/production_order_view.xml',
        'views/mrp_production_view.xml',
        'views/downtime_reasons_view.xml',
    ],
}

