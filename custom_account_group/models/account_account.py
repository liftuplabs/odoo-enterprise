from odoo import models, fields, api

class AccountAccount(models.Model):

    _inherit = "account.account"

    group_id = fields.Many2one(readonly=True, store=True)
    parent_group_id = fields.Many2one(related='group_id.parent_group_id', store=True, readonly=True)
    acc_current_balance = fields.Monetary(
        string='Balance',
        currency_field='currency_id',
        compute='_compute_acc_current_balance'
    )
    debit = fields.Monetary(
        string='Debit',
        currency_field='currency_id',
        compute='_compute_debit'
    )
    credit = fields.Monetary(
        string='Credit',
        currency_field='currency_id',
        compute='_compute_credit'
    )

    @api.depends_context('company')
    def _compute_debit(self):
        debits = {
            account.id: debit
            for account, debit in self.env['account.move.line']._read_group(
                domain=[('account_id', 'in', self.ids), ('parent_state', '=', 'posted'),
                        ('company_id', '=', self.env.company.id)],
                groupby=['account_id'],
                aggregates=['debit:sum'],
            )
        }
        for record in self:
            record.debit = debits.get(record.id, 0)

    @api.depends_context('company')
    def _compute_credit(self):
        credits = {
            account.id: credit
            for account, credit in self.env['account.move.line']._read_group(
                domain=[('account_id', 'in', self.ids), ('parent_state', '=', 'posted'),
                        ('company_id', '=', self.env.company.id)],
                groupby=['account_id'],
                aggregates=['credit:sum'],
            )
        }
        for record in self:
            record.credit = credits.get(record.id, 0)

    @api.depends_context('company')
    def _compute_acc_current_balance(self):
        balances = {
            account.id: balance
            for account, balance in self.env['account.move.line']._read_group(
                domain=[('account_id', 'in', self.ids), ('parent_state', '=', 'posted'),
                        ('company_id', '=', self.env.company.id)],
                groupby=['account_id'],
                aggregates=['balance:sum'],
            )
        }
        for record in self:
            record.acc_current_balance = balances.get(record.id, 0)

    @api.depends('code')
    def _compute_account_group(self):
        # 1. Run the original Odoo logic first
        super(AccountAccount, self)._compute_account_group()

        # 2. OVERRIDE: If an account is linked to a group via our new M2M,
        # force the group_id to that specific group.
        for account in self:
            # Search for any group where this account is explicitly selected
            manual_group = self.env['account.group'].search([
                ('account_ids', 'in', account.id)
            ], limit=1)

            if manual_group:
                account.group_id = manual_group