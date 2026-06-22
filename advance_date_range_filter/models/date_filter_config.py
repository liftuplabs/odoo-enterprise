from odoo import models, fields

class DateFilterConfig(models.Model):
    _name = 'date.filter.config'
    _description = 'Date Filter Configuration'

    name = fields.Char(compute='_compute_name', store=True)
    model_id = fields.Many2one('ir.model', string='Model', required=True, ondelete='cascade')
    model_name = fields.Char(related='model_id.model', readonly=True, store=True)
    date_field_id = fields.Many2one(
        'ir.model.fields', string='Date Field', required=True,
        domain="[('model_id', '=', model_id), ('ttype', 'in', ['date', 'datetime'])]",
        ondelete='cascade'
    )
    active = fields.Boolean(default=True)

    def _compute_name(self):
        for record in self:
            if record.model_id and record.date_field_id:
                record.name = f"{record.model_id.name} - {record.date_field_id.field_description}"
            else:
                record.name = "New Configuration"