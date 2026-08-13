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
    'depends': ['base', 'account', 'l10n_in', 'l10n_in_edi_ewaybill'],
    'data': [
        'security/ir.model.access.csv',
        'views/account_move_views.xml',
        'views/res_company_views.xml',
        'views/res_config_settings_views.xml',
        'views/report_invoice.xml',
        'views/eway_bill_report.xml',
        'views/account_payment_views.xml',
        'views/report_invoice_with_e_way_bill.xml',
        'wizard/account_move_print_wizard.xml',
        'wizard/eway_bill_print_wizard.xml',
        'wizard/invoice_and_eway_bill_print_wizard.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
