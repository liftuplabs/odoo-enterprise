from odoo import models, fields

class Partner(models.Model):
    _inherit = 'res.partner'

    udym_no = fields.Char(string="Udym No.")

