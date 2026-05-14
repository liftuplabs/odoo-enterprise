
{
    'name': 'Material Requisition',
    'version': '18.0',
    'category': 'stock',
    'sequence': 1,
    'author': 'Iprogrammer Solutions Pvt. Ltd.',
    'summary': 'For Material Requisition',
    'description': "This module is for material requisition.",
    'website': '',
    'currency': '',
    'license': 'Other proprietary',
    'depends': ['stock','repair'],
    'data': [
        'security/material_security.xml',
        'security/ir.model.access.csv',
        'views/materials_views.xml',
    ],
    'installable': True,
    'auto_install': False,
    'application': True,
}
