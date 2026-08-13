from odoo import models, fields, api

class InvoiceEwayCombinedPrintWizard(models.TransientModel):
    _name = 'invoice.eway.combined.print.wizard'
    _description = 'Invoice with E-Way Bill Print Wizard'

    move_id = fields.Many2one('account.move', string="Invoice")
    copy_type = fields.Selection([
        ('Original', 'Original'),
        ('Duplicate', 'Duplicate'),
        ('Triplicate', 'Triplicate'),
        ('Not Applicable', 'Not Applicable'),
        ('All', 'All')
    ], string="Print Copy", default='Original', required=True)

    @api.model
    def default_get(self, fields_list):
        # Automatically grab the current invoice ID when opened from the Download menu
        res = super().default_get(fields_list)
        if self.env.context.get('active_id'):
            res['move_id'] = self.env.context.get('active_id')
        return res

    def action_print(self):
        self.ensure_one()
        # Trigger the custom combined report action, passing our copy selection in context
        return self.env.ref('custom_invoice_format.action_report_invoice_with_ewaybill').with_context(
            custom_print_copy=self.copy_type
        ).report_action(self.move_id)