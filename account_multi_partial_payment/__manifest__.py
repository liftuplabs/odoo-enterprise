{
    'name': 'Multi Partial Payment Register',
    'version': '18.0.1.0.0',
    'summary': 'Register individual partial or full payments for multiple selected invoices at once.',
    'category': 'Accounting',
    'author': 'Custom Development',
    'depends': ['account'],
    'data': [
        'security/ir.model.access.csv',
        'wizard/multi_partial_payment_wizard_views.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}