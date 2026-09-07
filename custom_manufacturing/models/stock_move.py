# -*- coding: utf-8 -*-
from odoo import api, fields, models

class StockMove(models.Model):
    _inherit = 'stock.move'

    available_qty = fields.Float(
        string='Available QTY',
        compute='_compute_available_qty',
        digits='Product Unit of Measure',
        help='Available (unreserved) quantity of this product in the source location.'
    )

    @api.depends('product_id', 'location_id', 'state')
    def _compute_available_qty(self):
        for move in self:
            if move.product_id and move.location_id:
                # Use context to get the free_qty (available qty) specific to the move's source location
                move.available_qty = move.product_id.with_context(
                    location=move.location_id.id
                ).free_qty
            else:
                move.available_qty = 0.0