{
    'name': 'Tally Import',
    'version': '18.0.1.0',
    'category': 'Accounting',
    'summary': 'Import Tally',
    'description': """
        This module provides a wizard to import sales data from Tally-exported Excel files
        into Odoo as customer invoices. It handles parsing of the specific Tally format,
        creates necessary partners, products, and taxes if missing, and generates account.move records.
    """,
    'author': 'Your Name',
    'depends': ['account'],
    'external_dependencies': {'python': ['pandas', 'xlrd']},
    'data': [
        'security/ir.model.access.csv',
        'views/import_wizard.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}