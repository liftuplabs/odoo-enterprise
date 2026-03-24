# -*- coding: utf-8 -*-
################################################################################
#
#    Cybrosys Technologies Pvt. Ltd.
#
#    Copyright (C) 2025-TODAY Cybrosys Technologies(<https://www.cybrosys.com>).
#    Author: Manasa T P (odoo@cybrosys.com)
#
#    You can modify it under the terms of the GNU AFFERO
#    GENERAL PUBLIC LICENSE (AGPL v3), Version 3.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU AFFERO GENERAL PUBLIC LICENSE (AGPL v3) for more details.
#
#    You should have received a copy of the GNU AFFERO GENERAL PUBLIC LICENSE
#    (AGPL v3) along with this program.
#    If not, see <http://www.gnu.org/licenses/>.
#
################################################################################
from odoo import api, models


class SaleOrder(models.Model):
    """Module is inherited and function is created to create a sale
    order line with the scanned barcode of product"""
    _inherit = 'product.template'

    def action_print_serial_barcodes(self):
        StockQuant = self.env['stock.quant']
        all_quants = StockQuant.search([
            ('product_id', 'in', self.ids),
            ('lot_id', '!=', False),
            ('product_id', '=',self.id),
        ],limit=1)
        return self.env.ref('barcode_capturing_sale_purchase.action_serial_barcodes').report_action(all_quants)


class SaleOrder(models.Model):
    """Module is inherited and function is created to create a sale
    order line with the scanned barcode of product"""
    _inherit = 'sale.order'

    def repair_add_line_from_barcode(self, barcode):
        self.ensure_one()
        product = self.env['product.product'].search([('barcode', '=', barcode)], limit=1)


        self.line_ids = [(0, 0, {
            'product_id': product.id,
            'name': product.name,
            'product_uom_qty': 1,
            'price_unit': product.list_price,
        })]

    @api.model
    def barcode_search(self, last_code, order_id):
        """Sale Order line is created and product is added by checking
        the barcode. args contains the barcode of product and sale order id."""
        product = self.env['product.product'].search([('barcode', '=',
                                                       last_code)])
        if not product:
            return True
        else:
            sale_order = self.browse(order_id)
            if sale_order.order_line:
                for rec in sale_order.order_line:
                    if rec.product_id == product:
                        rec.product_uom_qty += 1
                        return
            sale_order.order_line.create({
                'order_id': sale_order.id,
                'product_id': product.id,
                'product_uom_qty': 1
            })
