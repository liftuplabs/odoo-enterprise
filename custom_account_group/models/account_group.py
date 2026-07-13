from odoo import models, fields, api
from odoo.exceptions import ValidationError

class AccountGroups(models.Model):
    _inherit = "account.group"
    _parent_name = "parent_group_id"
    _parent_store = True
    _order = 'complete_name, id'
    _rec_name = 'complete_name'
    _rec_names_search = ['complete_name', 'name']

    account_ids = fields.Many2many('account.account', string="Accounts")
    parent_group_id = fields.Many2one('account.group', string="Parent Group", domain="[('company_id', '=', company_id), ('id', '!=', id)]")
    complete_name = fields.Char(string="Complete Name", compute="_compute_complete_name", recursive=True, store=True)
    parent_path = fields.Char(index=True)

    @api.depends('complete_name')
    def _compute_display_name(self):
        for group in self:
            group.display_name = group.complete_name

    @api.depends('name', 'parent_group_id.complete_name')
    def _compute_complete_name(self):
        for group in self:
            if group.parent_group_id:
                group.complete_name = f"{group.parent_group_id.complete_name} / {group.name}"
            else:
                group.complete_name = group.name

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for record in records:
            if record.account_ids:
                # Direct update of the many2one field on the account
                record.account_ids.write({'group_id': record.id})
        return records

    def write(self, vals):
        # 1. Capture the state of accounts BEFORE the change
        # We store them in a mapping so we can compare later
        before_update = {record.id: record.account_ids for record in self}

        # 2. Perform the standard write
        res = super().write(vals)

        # 3. If account_ids was in the update, sync the group_id
        if 'account_ids' in vals:
            for record in self:
                old_accounts = before_update.get(record.id, self.env['account.account'])
                new_accounts = record.account_ids

                # Accounts that were removed: clear their group_id
                removed = old_accounts - new_accounts
                if removed:
                    removed.write({'group_id': False})

                # Accounts that were added or kept: set their group_id
                if new_accounts:
                    for account in new_accounts:
                        if account.group_id and account.group_id != record:
                            raise ValidationError(f"Account '{account.name}' is already assigned to another group '{account.group_id.name}'. Please remove it from that group first.")
                    new_accounts.write({'group_id': record.id})

        return res

