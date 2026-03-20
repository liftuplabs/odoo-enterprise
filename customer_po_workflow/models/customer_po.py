from django.utils.duration import duration_string
from pkg_resources import require
from odoo import api, Command, fields, models, modules, tools, _
from datetime import datetime, timedelta
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from collections import defaultdict
import json
from odoo.tools import float_compare, format_datetime, float_is_zero, float_round
from odoo.exceptions import UserError, ValidationError
import qrcode, base64
from io import BytesIO

class CustomerPO(models.Model):
    _name = 'customer.po'
    _description = 'Customer Purchase Order'

    name = fields.Char(string='PO Number', required=True)
    partner_id = fields.Many2one('res.partner', string='Customer', required=True)
    order_date = fields.Date(string='Order Date', default=fields.Date.today)
    line_ids = fields.One2many('customer.po.line', 'po_id', string='PO Lines')
    po_state = fields.Selection([('draft','Draft'),('confirmed','Confirmed')], default='draft')
    sale_order_id = fields.Many2one('sale.order', string='Sale Order', readonly=True)
    production_count = fields.Integer(string='Production Orders', compute='_compute_production_count')
    stock_count = fields.Integer(string='Stock Count', compute='_compute_stock_count')

    def action_confirm(self):
        so_obj = self.env['sale.order']
        for po in self:
            so = so_obj.create({
                'partner_id': po.partner_id.id,
                'origin': po.name,
                'order_line': [(0,0,{
                    'product_id': line.product_id.id,
                    'product_uom_qty': line.qty,
                    'price_unit': line.price_unit,
                    'product_uom': line.uom_id.id,
                }) for line in po.line_ids]
            })
            po.sale_order_id = so.id
            po.po_state = 'confirmed'

    def _compute_production_count(self):
        """Count linked manufacturing orders"""
        for po in self:
            count = self.env['mrp.production'].search_count([('customer_po_id', '=', po.id)])
            po.production_count = count

    def _compute_stock_count(self):
        """Count linked manufacturing orders"""
        for po in self:
            count = self.env['stock.quant'].search_count([('customer_po', '=', po.name),('inventory_quantity_auto_apply', '=', 1),
            ('location_id.usage', '=', 'internal')])
            po.stock_count = count

    def action_view_stock(self):
        """Open linked Sale Order"""
        self.ensure_one()
        return {
            'name': 'Sale Order',
            'type': 'ir.actions.act_window',
            'res_model': 'stock.quant',
            'view_mode': 'list',
            'domain': [('customer_po', '=', self.name),('inventory_quantity_auto_apply', '=', 1),
            ('location_id.usage', '=', 'internal')],
        }

    def action_view_sale_order(self):
        """Open linked Sale Order"""
        self.ensure_one()
        return {
            'name': 'Sale Order',
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'view_mode': 'form',
            'res_id': self.sale_order_id.id,
        }

    def action_view_production_orders(self):
        """Open related Manufacturing Orders"""
        self.ensure_one()
        return {
            'name': 'Manufacturing Orders',
            'type': 'ir.actions.act_window',
            'res_model': 'mrp.production',
            'view_mode': 'list,form',
            'domain': [('customer_po_id', '=', self.id)],
        }

class CustomerPOLine(models.Model):
    _name = 'customer.po.line'

    po_id = fields.Many2one('customer.po', string='PO Reference', required=True)
    product_id = fields.Many2one('product.product', string='Product', required=True)
    qty = fields.Float(string='Quantity', required=True)
    uom_id = fields.Many2one('uom.uom', string='Unit of Measure')
    price_unit = fields.Float(string='Unit Price')


    @api.onchange('product_id')
    def change_line_ids(self):
        for rec in self:
            if rec.product_id and rec.product_id.uom_id:
                rec.uom_id = rec.product_id.uom_id.id
            if rec.product_id and rec.product_id.lst_price:
                rec.price_unit = rec.product_id.lst_price

