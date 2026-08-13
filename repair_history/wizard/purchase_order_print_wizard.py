from odoo import models, fields, api

class PurchaseOrderPrintWizard(models.TransientModel):
    _name = 'purchase.order.print.wizard'
    _description = 'Purchase Order Print Wizard'

    order_id = fields.Many2one('purchase.order', string="Purchase Order")
    copy_type = fields.Selection([
        ('Original', 'Original'),
        ('Duplicate', 'Duplicate'),
        ('Triplicate', 'Triplicate'),
        ('Not Applicable', 'Not Applicable'),
        ('All', 'All')
    ], string="Print Copy", default='Original', required=True)

    @api.model
    def default_get(self, fields_list):
        # Automatically grab the current purchase order ID when opened from the Print/Download menu
        res = super().default_get(fields_list)
        if self.env.context.get('active_id'):
            res['order_id'] = self.env.context.get('active_id')
        return res

    def action_print(self):
        self.ensure_one()
        # Trigger the standard purchase order report action, passing our copy selection in context
        return self.env.ref('purchase.action_report_purchase_order').with_context(
            custom_print_copy=self.copy_type
        ).report_action(self.order_id)