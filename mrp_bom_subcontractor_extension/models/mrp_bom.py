from odoo import models, fields


class MrpBom(models.Model):
    _inherit = 'mrp.bom'

    is_external_subcontractor = fields.Boolean(
        string='Needs Subcontractor',
        default=False,
        help="Check this if an external subcontractor is involved in this internal BoM."
    )

    external_subcontractor_id = fields.Many2one(
        'res.partner',
        string='Subcontractor',
        help="Select the partner handling the subcontracted operation."
    )