from odoo import models, fields, api

class RepairOrderPrintWizard(models.TransientModel):
    _name = 'repair.order.print.wizard'
    _description = 'Repair Order Print Wizard'

    repair_id = fields.Many2one('repair.order', string="Repair Order")
    copy_type = fields.Selection([
        ('Original', 'Original'),
        ('Duplicate', 'Duplicate'),
        ('Triplicate', 'Triplicate'),
        ('Not Applicable', 'Not Applicable'),
        ('All', 'All')
    ], string="Print Copy", default='Original', required=True)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if self.env.context.get('active_id'):
            res['repair_id'] = self.env.context.get('active_id')
        return res

    def action_print(self):
        self.ensure_one()
        return self.env.ref('repair.action_report_repair_order').with_context(
            custom_print_copy=self.copy_type
        ).report_action(self.repair_id)