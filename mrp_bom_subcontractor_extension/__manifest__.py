{
    'name': 'MRP BoM Subcontractor Extension',
    'version': '18.0.1.0.0',
    'category': 'Manufacturing/Manufacturing',
    'summary': 'Adds custom subcontractor tracking fields to the Bill of Materials',
    'description': """
        This module adds a boolean field and a partner selection field to the BoM 
        to track external subcontractors without changing the BoM type to Subcontracting.
    """,
    'author': 'Your Company',
    'depends': ['mrp', 'purchase', 'stock', 'mrp_subcontracting_purchase'],
    'data': [
        'views/mrp_bom_views.xml',
        'views/mrp_production_views.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}