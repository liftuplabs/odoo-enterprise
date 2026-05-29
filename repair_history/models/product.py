from enum import unique

from odoo import api, Command, fields, models, modules, tools, _
from odoo.exceptions import UserError, ValidationError

class ProductTemplate(models.Model):

    _inherit = 'product.template'

    @api.constrains('name', 'default_code')
    def _check_unique_fields(self):
        for record in self:
            if record.name:
                domain = [('name', '=', record.name), ('id', '!=', record.id)]
                if self.search_count(domain) > 0:
                    raise ValidationError(_("The product name '%s' already exists!", record.name))

            if record.default_code:
                domain = [('default_code', '=', record.default_code), ('id', '!=', record.id)]
                if self.search_count(domain) > 0:
                    raise ValidationError(_("The part code '%s' is already exists!", record.default_code))

class ProductProduct(models.Model):

    _inherit = 'product.product'

    @api.constrains('name', 'default_code')
    def _check_unique_fields(self):
        for record in self:
            if record.name:
                domain = [('name', '=', record.name), ('id', '!=', record.id)]
                if self.search_count(domain) > 0:
                    raise ValidationError(_("The product name '%s' already exists!", record.name))

            if record.default_code:
                domain = [('default_code', '=', record.default_code), ('id', '!=', record.id)]
                if self.search_count(domain) > 0:
                    raise ValidationError(_("The part code '%s' is already exists!", record.default_code))