# -*- coding: utf-8 -*-
# Part of BrowseInfo. See LICENSE file for full copyright and licensing details.
{
    'name': "Visitor/Guest Management Software",
    'version': "18.0.0.0",
    'category': "Extra Tools",
    'summary': "Create Visitors Contact Details Guest Management Software Visitor Management App Hotel Visitor Management Visitor Tracking Software Visit Entry Pass System Guest Visitor Meeting Request Company Visitors Pass Office Visitors Pass Front Office Desk Visitors",
    'description': """  

        Visitor/Guest Management Software Odoo App helps users to managing visitors with its details. Using this app know the reason of meeting, who meets to whom, visitor contact details, visit type, check in and check out details, track visitor details, increase securities of visitor, pass can be sent by email and printed.

    """,
    'author': 'BROWSEINFO',
    "price": 15,
    "currency": 'EUR',
    'website': 'https://www.browseinfo.com/demo-request?app=bi_visitor_management&version=18&edition=Community',
    'depends': ['base', 'contacts', 'hr'],
    'data': [
        'security/visitor_security.xml',
        'security/ir.model.access.csv',
        'data/visitor_data.xml',
        'report/report_visitor_pass_template.xml',
        'report/report_visitor_pass.xml',
        'data/visitor_mail_template.xml',
        'views/visitor_category_views.xml',
        'views/visitor_type_views.xml',
        'views/visitor_views.xml',
    ],
    'license':'OPL-1',
    'installable': True,
    'auto_install': False,
    'live_test_url':'https://www.browseinfo.com/demo-request?app=bi_visitor_management&version=18&edition=Community',
    "images":['static/description/Banner.gif'],
}
