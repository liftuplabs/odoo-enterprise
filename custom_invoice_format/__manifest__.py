{
    'name': 'Custom Invoice Format (Tax Invoice)',
    'version': '18.0.1.0.0',
    'category': 'Accounting/Accounting',
    'summary': 'Custom Tax Invoice Key Features: Consignee/Buyer Split, Dispatch Details, DSG Signature.',
    'description': """
        Implements a custom "Tax Invoice" PDF report.
        New Fields on Invoice:
        - Dispatch Doc No.
        - Terms of Delivery
        - Delivery Note Date
        - Supplier Reference & Other Reference
        - Mode of Payment
        
        Report Features:
        - Side-by-side Consignee (Ship To) and Buyer (Bill To)
        - Detailed Transport/Delivery table.
        - DSG Signature placeholder.
    """,
    'author': 'Antigravity',
    'depends': ['base', 'account', 'l10n_in'],
    'data': [
        'views/account_move_views.xml',
        'views/res_company_views.xml',
        'views/res_config_settings_views.xml',
        'views/report_invoice.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
