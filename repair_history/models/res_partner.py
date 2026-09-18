from odoo import models, fields, api
from odoo.exceptions import ValidationError

class Partner(models.Model):
    _inherit = 'res.partner'

    udym_no = fields.Char(string="Udym No.")

    @api.constrains('name')
    def _check_unique_name(self):
        for rec in self:
            if rec.name:
                # Search for any other partner with the same name, excluding the current record
                # Using '=ilike' makes the check case-insensitive (e.g., "John" and "john" will be treated as duplicates)
                duplicate_exists = self.env['res.partner'].search_count([
                    ('name', '=ilike', rec.name),
                    ('id', '!=', rec.id)
                ])

                if duplicate_exists > 0:
                    raise ValidationError(f"A contact with the name '{rec.name}' already exists!")

