from enum import unique

from odoo import api, Command, fields, models, modules, tools, _
from odoo.exceptions import UserError, ValidationError
from lxml import etree

class ProductTemplate(models.Model):

    _inherit = 'product.template'

    service_product_ids = fields.Many2many('product.product', string='Service Products', tracking=True)
    item_code = fields.Char(string='Item Code', tracking=True)
    repair_min_qty = fields.Float(string="Min Repair Qty", default=0.0,
                                  help="Minimum quantity allowed when used in a Repair Order.")
    repair_max_qty = fields.Float(string="Max Repair Qty", default=0.0,
                                  help="Maximum quantity allowed when used in a Repair Order. (0 means no limit)")

    # @api.constrains('name', 'default_code')
    @api.constrains('name')
    def _check_unique_fields(self):
        for record in self:
            if record.name:
                domain = [('name', '=', record.name), ('id', '!=', record.id)]
                if self.search_count(domain) > 0:
                    raise ValidationError(_("The product name '%s' already exists!", record.name))

            # if record.default_code:
            #     domain = [('default_code', '=', record.default_code), ('id', '!=', record.id)]
            #     if self.search_count(domain) > 0:
            #         raise ValidationError(_("The part code '%s' is already exists!", record.default_code))

    @api.model_create_multi
    def create(self, vals_list):
        # Check if the user is NOT an inventory manager/admin
        if not self.env.user.has_group('stock.group_stock_manager'):
            raise UserError(_("Access Denied: Only Inventory Administrators can create products."))
        return super(ProductTemplate, self).create(vals_list)

    def unlink(self):
        # Check if the user is NOT an inventory manager/admin
        if not self.env.user.has_group('stock.group_stock_manager'):
            raise UserError(_("Access Denied: Only Inventory Administrators can delete products."))
        return super(ProductTemplate, self).unlink()

    @api.model
    def get_views(self, views, options=None):
        res = super(ProductTemplate, self).get_views(views, options=options)

        # If the user is an admin/manager, keep standard behavior intact
        if self.env.user.has_group('stock.group_stock_manager'):
            return res

        # Dynamically inject create="0" and delete="0" for normal users
        for view_type, view_meta in res.get('views', {}).items():
            if 'arch' in view_meta:
                arch_xml = etree.fromstring(view_meta['arch'])
                if arch_xml.tag in ['form', 'tree', 'list', 'kanban']:
                    arch_xml.set('create', '0')
                    arch_xml.set('delete', '0')
                    view_meta['arch'] = etree.tostring(arch_xml, encoding='unicode')

        return res

class ProductProduct(models.Model):

    _inherit = 'product.product'

    item_code = fields.Char(string='Item Code', tracking=True)

    # @api.constrains('name', 'default_code')
    @api.constrains('name')
    def _check_unique_fields(self):
        for record in self:
            if record.name:
                domain = [('name', '=', record.name), ('id', '!=', record.id)]
                if self.search_count(domain) > 0:
                    raise ValidationError(_("The product name '%s' already exists!", record.name))

            # if record.default_code:
            #     domain = [('default_code', '=', record.default_code), ('id', '!=', record.id)]
            #     if self.search_count(domain) > 0:
            #         raise ValidationError(_("The part code '%s' is already exists!", record.default_code))

    @api.model_create_multi
    def create(self, vals_list):
        # Block creation for non-managers
        if not self.env.user.has_group('stock.group_stock_manager'):
            raise UserError(_("Access Denied: Only Inventory Administrators can create product variants."))
        return super(ProductProduct, self).create(vals_list)

    def unlink(self):
        # Block deletion for non-managers
        if not self.env.user.has_group('stock.group_stock_manager'):
            raise UserError(_("Access Denied: Only Inventory Administrators can delete product variants."))
        return super(ProductProduct, self).unlink()

    @api.model
    def get_views(self, views, options=None):
        res = super(ProductProduct, self).get_views(views, options=options)

        # Admin bypass
        if self.env.user.has_group('stock.group_stock_manager'):
            return res

        # Strip create and delete capabilities from all variant views
        for view_type, view_meta in res.get('views', {}).items():
            if 'arch' in view_meta:
                arch_xml = etree.fromstring(view_meta['arch'])
                if arch_xml.tag in ['form', 'tree', 'list', 'kanban']:
                    arch_xml.set('create', '0')
                    arch_xml.set('delete', '0')
                    view_meta['arch'] = etree.tostring(arch_xml, encoding='unicode')

        return res