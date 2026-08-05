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
        # update account_followup
        'views/res_partner_view.xml',
        # 'views/report_invoice.xml',
        'views/product_template_views.xml',
        'views/stock_picking_views.xml',
        'views/stock_move_line_views.xml',
        'views/sale_order_views.xml',
        'views/check_list.xml',
        'views/hr_employee.xml',
        'views/res_company.xml',
        'views/material_out_print_wizard_views.xml',
        'reports/material_out_report.xml',
        'reports/sale_order_report.xml',
        'reports/purchase_order_report.xml',
        'reports/repair_order_report.xml',
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
