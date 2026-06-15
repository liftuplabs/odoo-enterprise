# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': 'Repair History',
    'description': """
===============================================
    """,
    'version': '18.0',
    'category': 'productivity',
    'auto_install': True,
    'depends': [
        'web',
        'hr',
        'base',
        'stock',
        'mail',
        'repair',
        'account',
        # 'hr_attendance',
        'web',
        'purchase',
        'l10n_in'
    ],
    'data': [
        'data/ir_action_data.xml',
        'security/security.xml',
        'security/ir.model.access.csv',
        'views/custom.xml',
        # 'views/account_move_view.xml',
        'views/res_partner_view.xml',
        # 'views/report_invoice.xml',
        'views/product_template_views.xml',
        'views/stock_picking_views.xml',
        'views/stock_move_line_views.xml',
        'views/sale_order_views.xml',
        'views/report_sale_order.xml',
        'views/report_purchase_order.xml',
        'views/check_list.xml',
        'views/hr_employee.xml',
        'views/res_company.xml',
        'reports/material_out_report.xml',
        ],

    'assets': {
        'web.assets_backend': [
            'repair_history/static/src/js/timer.js',
            'repair_history/static/src/xml/timer.xml',
        ],
    },


    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
