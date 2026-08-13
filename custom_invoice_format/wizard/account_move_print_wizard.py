from odoo import models, fields, api

class AccountMovePrintWizard(models.TransientModel):
    _name = 'account.move.print.wizard'
    _description = 'Invoice Print Wizard'

    move_id = fields.Many2one('account.move', string="Invoice", required=True)
    copy_type = fields.Selection([
        ('Original', 'Original'),
        ('Duplicate', 'Duplicate'),
        ('Triplicate', 'Triplicate'),
        ('Not Applicable', 'Not Applicable'),
        ('All', 'All')
    ], string="Print Copy", default='Original', required=True)

    # @api.model
    # def default_get(self, fields_list):
    #     # Automatically grab the current invoice ID when opened from the Download menu
    #     res = super().default_get(fields_list)
    #     if self.env.context.get('active_id'):
    #         res['move_id'] = self.env.context.get('active_id')
    #     return res

    def action_print(self):
        self.ensure_one()
        # Trigger the standard invoice print action, passing our copy selection in context
        return self.env.ref('account.account_invoices').with_context(
            custom_print_copy=self.copy_type
        ).report_action(self.move_id)