from odoo import models, fields, api

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    # Invisible compute fields to check user rights
    is_sale_price_hidden = fields.Boolean(compute='_compute_hide_prices')
    is_cost_price_hidden = fields.Boolean(compute='_compute_hide_prices')

    @api.depends_context('uid')
    def _compute_hide_prices(self):
        for record in self:
            # Checks if the current user has the checkbox ticked
            record.is_sale_price_hidden = self.env.user.has_group('scs_hide_menu_user_wise.group_hide_sale_price')
            record.is_cost_price_hidden = self.env.user.has_group('scs_hide_menu_user_wise.group_hide_cost_price')