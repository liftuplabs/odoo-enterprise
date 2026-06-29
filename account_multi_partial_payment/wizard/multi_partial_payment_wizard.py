from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


class MultiPartialPaymentWizard(models.TransientModel):
    _name = 'multi.partial.payment.wizard'
    _description = 'Multi Partial Payment Wizard'

    payment_date = fields.Date(
        string="Payment Date",
        default=fields.Date.context_today,
        required=True
    )
    journal_id = fields.Many2one(
        'account.journal',
        string='Journal',
        required=True,
        domain=[('type', 'in', ('bank', 'cash'))]
    )
    line_ids = fields.One2many(
        'multi.partial.payment.wizard.line',
        'wizard_id',
        string="Invoices"
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        active_ids = self.env.context.get('active_ids')
        active_model = self.env.context.get('active_model')

        if active_model == 'account.move' and active_ids:
            moves = self.env['account.move'].browse(active_ids).filtered(
                lambda m: m.state == 'posted' and m.payment_state in ('not_paid', 'partial')
            )

            if not moves:
                raise UserError(_("No valid open invoices selected for payment."))

            lines = []
            for move in moves:
                lines.append((0, 0, {
                    'move_id': move.id,
                    'partner_id': move.partner_id.id,
                    'amount_residual': move.amount_residual,
                    'amount_to_pay': move.amount_residual,  # Defaults to full payment
                    'currency_id': move.currency_id.id,
                }))
            res['line_ids'] = lines
        return res

    def action_create_payments(self):
        """ Iterates through custom wizard lines and processes standard payments. """
        PaymentRegister = self.env['account.payment.register']

        for line in self.line_ids:
            if line.amount_to_pay <= 0:
                raise ValidationError(
                    f"The payment amount for invoice {line.move_id.name} must be greater than zero."
                )

            if line.amount_to_pay > line.amount_residual:
                raise UserError(_("Payment amount cannot exceed the residual amount for invoice %s", line.move_id.name))

            # Find the un-reconciled receivable/payable lines for the individual move
            move_lines = line.move_id.line_ids.filtered(
                lambda l: l.account_id.account_type in ('asset_receivable', 'liability_payable') and not l.reconciled
            )

            if not move_lines:
                continue

            # Context override mimics a single-invoice click inside core register action
            ctx = dict(self.env.context, active_model='account.move.line', active_ids=move_lines.ids)

            wizard_fields = list(PaymentRegister._fields.keys())
            default_vals = PaymentRegister.with_context(**ctx).default_get(wizard_fields)

            # 2. Inject our custom partial payment details
            default_vals.update({
                'journal_id': self.journal_id.id,
                'payment_date': self.payment_date,
                'amount': line.amount_to_pay,
                'group_payment': False,
                'communication': line.move_id.name,
            })

            # 3. Create the fully-formed wizard record
            register_wizard = PaymentRegister.with_context(**ctx).create(default_vals)

            payment_record = register_wizard._create_payments()
            if payment_record:
                payment_record.action_validate()

        return {'type': 'ir.actions.act_window_close'}


class MultiPartialPaymentWizardLine(models.TransientModel):
    _name = 'multi.partial.payment.wizard.line'
    _description = 'Multi Partial Payment Wizard Line'

    wizard_id = fields.Many2one('multi.partial.payment.wizard')
    move_id = fields.Many2one('account.move', string="Invoice", required=True)
    partner_id = fields.Many2one('res.partner', string="Customer", required=True)
    currency_id = fields.Many2one('res.currency', related='move_id.currency_id')
    amount_residual = fields.Monetary(string="Amount Due", readonly=True)
    amount_to_pay = fields.Monetary(string="Payment Received")
    allowed_move_ids = fields.Many2many(
        'account.move',
        compute='_compute_allowed_moves'
    )

    @api.depends('partner_id')
    def _compute_allowed_moves(self):
        allowed_move_types = ('out_invoice', 'in_invoice')  # Fallback

        active_ids = self.env.context.get('active_ids')
        active_model = self.env.context.get('active_model')

        if active_model == 'account.move' and active_ids:
            selected_moves = self.env['account.move'].browse(active_ids)
            if selected_moves:
                if selected_moves[0].move_type == 'in_invoice':
                    allowed_move_types = ('in_invoice',)  # Lock to Vendor Bills
                elif selected_moves[0].move_type == 'out_invoice':
                    allowed_move_types = ('out_invoice',)  # Lock to Customer Invoices

        for line in self:
            domain = [
                ('state', '=', 'posted'),
                ('payment_state', 'in', ('not_paid', 'partial')),
                ('move_type', 'in', allowed_move_types)
            ]

            if line.partner_id:
                domain.append(('partner_id', '=', line.partner_id.id))

            line.allowed_move_ids = self.env['account.move'].search(domain)

    @api.onchange('move_id')
    def _onchange_move_id(self):
        for line in self:
            if line.move_id:
                line.partner_id = line.move_id.partner_id
                line.amount_residual = line.move_id.amount_residual
                line.amount_to_pay = line.move_id.amount_residual  # Default to full payment