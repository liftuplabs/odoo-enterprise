from odoo import models, fields, api

class MaterialOutPrintWizard(models.TransientModel):
    _name = 'material.out.print.wizard'
    _description = 'Material Out Print Wizard'

    picking_id = fields.Many2one('stock.picking', string="Delivery Order", required=True)
    copy_type = fields.Selection([
        ('Original', 'Original'),
        ('Duplicate', 'Duplicate'),
        ('Triplicate', 'Triplicate'),
        ('Not Applicable', 'Not Applicable'),
        ('All', 'All')
    ], string="Print Copy", default='Original', required=True)

    def action_print(self):
        self.ensure_one()
        # Pass the user's selection to the report via the context
        return self.env.ref('stock.action_report_delivery').with_context(
            custom_print_copy=self.copy_type
        ).report_action(self.picking_id)