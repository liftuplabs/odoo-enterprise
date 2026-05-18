from collections import Counter, defaultdict

from odoo import _, api, fields, tools, models, Command
from odoo.exceptions import UserError, ValidationError
from odoo.osv import expression
from odoo.tools import OrderedSet, format_list, groupby
from odoo.tools.float_utils import float_compare, float_is_zero, float_round


class StockMoveLineInt(models.Model):
    _inherit = "stock.move.line"

    lot_name = fields.Char('Lot/Serial Number Name', tracking=True)
    customer_lot_name = fields.Char('Serial Number (Customer)')

    def _get_tracked_fields(self):
        """ Add lot_name to the list of fields tracked in the picking chatter """
        res = super()._get_tracked_fields()
        res.add('lot_name')
        return res

    def write(self, vals):
        # Modified check: Allow product_id changes in 'draft' and 'assigned'
        old_lots = {ml.id: ml.lot_id.display_name or ml.lot_name for ml in self}

        if 'product_id' in vals and any(
                vals.get('state', ml.state) not in ['draft', 'assigned'] and vals['product_id'] != ml.product_id.id for
                ml in self):
            raise UserError(_("Changing the product is only allowed in 'Draft' or 'Ready' states."))

        if ('lot_id' in vals or 'quant_id' in vals) and len(self.product_id) > 1:
            raise UserError(_("Changing the Lot/Serial number for move lines with different products is not allowed."))

        moves_to_recompute_state = self.env['stock.move']
        triggers = [
            ('location_id', 'stock.location'),
            ('location_dest_id', 'stock.location'),
            ('lot_id', 'stock.lot'),
            ('package_id', 'stock.quant.package'),
            ('result_package_id', 'stock.quant.package'),
            ('owner_id', 'res.partner'),
            ('product_uom_id', 'uom.uom')
        ]
        if vals.get('quant_id'):
            vals.update(self._copy_quant_info(vals))
        updates = {}
        for key, model in triggers:
            if key in vals:
                updates[key] = vals[key] if isinstance(vals[key], models.BaseModel) else self.env[model].browse(
                    vals[key])

        if 'result_package_id' in updates:
            for ml in self.filtered(lambda ml: ml.package_level_id):
                if updates.get('result_package_id'):
                    ml.package_level_id.package_id = updates.get('result_package_id')
                else:
                    package_level = ml.package_level_id
                    ml.package_level_id = False
                    if not package_level.move_line_ids:
                        package_level.unlink()

        if (updates and {'result_package_id'}.difference(updates.keys())) or 'quantity' in vals:
            for ml in self:
                if not ml.product_id.is_storable or ml.state == 'done':
                    continue
                if 'quantity' in vals or 'product_uom_id' in vals:
                    new_ml_uom = updates.get('product_uom_id', ml.product_uom_id)
                    new_reserved_qty = new_ml_uom._compute_quantity(
                        vals.get('quantity', ml.quantity), ml.product_id.uom_id, rounding_method='HALF-UP')
                    if float_compare(new_reserved_qty, 0, precision_rounding=ml.product_id.uom_id.rounding) < 0:
                        raise UserError(_('Reserving a negative quantity is not allowed.'))
                else:
                    new_reserved_qty = ml.quantity_product_uom

                if not float_is_zero(ml.quantity_product_uom, precision_rounding=ml.product_uom_id.rounding):
                    ml._synchronize_quant(-ml.quantity_product_uom, ml.location_id, action="reserved")

                if not ml.move_id._should_bypass_reservation(updates.get('location_id', ml.location_id)):
                    ml._synchronize_quant(
                        new_reserved_qty, updates.get('location_id', ml.location_id), action="reserved",
                        lot=updates.get('lot_id', ml.lot_id), package=updates.get('package_id', ml.package_id),
                        owner=updates.get('owner_id', ml.owner_id))

                if ('quantity' in vals and vals['quantity'] != ml.quantity) or 'product_uom_id' in vals:
                    moves_to_recompute_state |= ml.move_id

        mls = self.env['stock.move.line']
        if updates or 'quantity' in vals:
            next_moves = self.env['stock.move']
            mls = self.filtered(lambda ml: ml.move_id.state == 'done' and ml.product_id.is_storable)
            if not updates:
                mls = mls.filtered(lambda ml: not float_is_zero(ml.quantity - vals['quantity'],
                                                                precision_rounding=ml.product_uom_id.rounding))
            for ml in mls:
                in_date = \
                ml._synchronize_quant(-ml.quantity_product_uom, ml.location_dest_id, package=ml.result_package_id)[1]
                ml._synchronize_quant(ml.quantity_product_uom, ml.location_id, in_date=in_date)
                next_moves |= ml.move_id.move_dest_ids.filtered(lambda move: move.state not in ('done', 'cancel'))
                if ml.picking_id:
                    ml._log_message(ml.picking_id, ml, 'stock.track_move_template', vals)
            move_done = mls.move_id
            if move_done:
                move_done._check_quantity()

        if 'date' not in vals and ('product_uom_id' in vals or 'quantity' in vals or vals.get('picked', False)):
            updated_ml_ids = set()
            for ml in self:
                if ml.state in ['draft', 'cancel', 'done']:
                    continue
                if vals.get('picked', False) and not ml.picked:
                    updated_ml_ids.add(ml.id)
                    continue
                if ('quantity' in vals or 'product_uom_id' in vals) and ml.picked:
                    new_qty = updates.get('product_uom_id', ml.product_uom_id)._compute_quantity(
                        vals.get('quantity', ml.quantity), ml.product_id.uom_id, rounding_method='HALF-UP')
                    old_qty = ml.product_uom_id._compute_quantity(ml.quantity, ml.product_id.uom_id,
                                                                  rounding_method='HALF-UP')
                    if float_compare(old_qty, new_qty, precision_rounding=ml.product_uom_id.rounding) < 0:
                        updated_ml_ids.add(ml.id)
            self.env['stock.move.line'].browse(updated_ml_ids).date = fields.Datetime.now()

        res = models.Model.write(self, vals)

        for ml in mls:
            available_qty, dummy = ml._synchronize_quant(-ml.quantity_product_uom, ml.location_id)
            ml._synchronize_quant(ml.quantity_product_uom, ml.location_dest_id, package=ml.result_package_id)
            if available_qty < 0:
                ml._free_reservation(
                    ml.product_id, ml.location_id,
                    abs(available_qty), lot_id=ml.lot_id, package_id=ml.package_id,
                    owner_id=ml.owner_id)

        if updates or 'quantity' in vals:
            next_moves._do_unreserve()
            next_moves._action_assign()

        if moves_to_recompute_state:
            moves_to_recompute_state._recompute_state()

        if 'lot_id' in vals or 'lot_name' in vals:
            for ml in self:
                if ml.picking_id:
                    # Determine the new value
                    new_val = ml.lot_id.display_name or ml.lot_name or _('None')
                    old_val = old_lots.get(ml.id) or _('None')

                    if old_val != new_val:
                        ml.picking_id.message_post(
                            body=_("Serial Number updated on product %s from %s to %s") % (ml.move_id.product_id.name, old_val, new_val)
                        )

        return res
