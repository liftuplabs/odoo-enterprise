from odoo import models, fields, api, _
from datetime import datetime
import logging
import json
import base64
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

try:
    from num2words import num2words
except ImportError:
    _logger.warning("The num2words python library is not installed.")
    num2words = None

class AccountMove(models.Model):
    _inherit = 'account.move'

    dispatch_doc_no = fields.Char(string='Dispatch Doc No.')
    dispatch_through = fields.Char(string='Dispatched Through')
    destination = fields.Char(string='Destination')
    terms_of_delivery = fields.Text(string='Terms of Delivery')

    supplier_reference = fields.Char(string='Supplier Reference')
    other_reference = fields.Char(string='Other Reference')

    delivery_note = fields.Char(string='Delivery Note')
    delivery_note_date = fields.Date(string='Delivery Note Date')

    mode_of_payment = fields.Char(string='Mode/Terms of Payment')

    buyers_order_no = fields.Char(string="Buyer's Order No.")
    buyers_order_date = fields.Date(string="Buyer's Order Date")

    eway_bill_no = fields.Char(
        string='Ewb No.',
    )
    eway_bill_date = fields.Date(
        string='Ewb Date',
    )
    eway_bill_valid_till = fields.Date(
        string='Ewb Valid Till',
    )
    transaction_type = fields.Selection(
        selection=[
            ('1', 'Regular'),
            ('2', 'Bill To - Ship To'),
            ('3', 'Bill From - Dispatch From'),
            ('4', 'Combination of 2 and 3')
        ],
        string='Transaction Type',
        help='Select the transaction type for this invoice.'
    )


    # 1. Spacing and Typography
    custom_layout_size = fields.Selection(
        selection=[
            ('auto', 'Auto (Based on Lines)'),
            ('compact', 'Compact'),
            ('dense', 'Dense (30+ Lines)')
        ],
        string='Layout Size',
        default='auto',
        help='Controls the padding and line height of the printed document.'
    )

    custom_font_size = fields.Selection(
        selection=[
            ('small', 'Small (10px)'),
            ('standard', 'Standard (12px)'),
            ('medium', 'Medium (13px)'),
            ('large', 'Large (14px)'),
            ('xlarge', 'Extra Large (15px)')
        ],
        string='Base Font Size',
        default='large'
    )

    # 2. Table Configurations
    custom_table_style = fields.Selection(
        selection=[
            ('bordered', 'Fully Bordered'),
            ('minimal', 'Minimal (Horizontal Lines Only)'),
            ('striped', 'Striped Rows')
        ],
        string='Table Style',
        default='striped'
    )

    custom_bold_table_data = fields.Boolean(
        string='Bold Table Data',
        default=False,
        help='Check this to make all text within the product lines bold.'
    )

    sale_order_name = fields.Char(
        string="Sale Order",
        compute="_compute_sale_order_info",
        store=True
    )
    sale_order_date = fields.Datetime(
        string="Sale Date",
        compute="_compute_sale_order_info",
        store=True
    )

    @api.depends('invoice_line_ids.sale_line_ids.order_id')
    def _compute_sale_order_info(self):
        for move in self:
            # Find all sale orders linked to this invoice's lines
            sale_orders = move.invoice_line_ids.mapped('sale_line_ids.order_id')

            if sale_orders:
                # If multiple SOs exist for one invoice, join them with a comma
                move.sale_order_name = ', '.join(sale_orders.mapped('name'))
                # Fetch the date of the first related sale order
                move.sale_order_date = sale_orders[0].date_order
            else:
                # Fallback to standard invoice_origin if not linked via lines
                move.sale_order_name = move.invoice_origin or False
                move.sale_order_date = False

    # 3. Custom INR Word Formatter
    def _get_inr_amount_in_words(self, amount):
        self.ensure_one()
        if num2words:
            try:
                integer_part = int(amount)
                fractional_part = int(round((amount - integer_part) * 100))

                # Force Indian numbering (Lakhs/Crores)
                words = num2words(integer_part, lang='en_IN').title().replace(',', '')
                result = words

                if fractional_part > 0:
                    dec_words = num2words(fractional_part, lang='en_IN').title().replace(',', '')
                    result += f" and {dec_words} Paise"

                return result + " Only"
            except Exception:
                pass

        # Fallback to standard Odoo method if library behaves unexpectedly
        return self.currency_id.amount_to_text(amount) + " Only"

    def action_compute_eway_bill_info(self):
        for move in self:
            move.eway_bill_no = False
            move.eway_bill_date = False
            move.eway_bill_valid_till = False

            response_json = move._get_l10n_in_edi_ewaybill_response_json()

            if not response_json:
                continue

            ewb_no = response_json.get('EwbNo')
            ewb_date_str = response_json.get('EwbDt')
            ewb_valid_str = response_json.get('EwbValidTill')

            if ewb_no:
                move.eway_bill_no = str(ewb_no)

            try:
                if ewb_date_str:
                    move.eway_bill_date = datetime.strptime(
                        ewb_date_str,
                        '%Y-%m-%d %H:%M:%S'
                    ).date()

                if ewb_valid_str:
                    move.eway_bill_valid_till = datetime.strptime(
                        ewb_valid_str,
                        '%Y-%m-%d %H:%M:%S'
                    ).date()

            except ValueError as e:
                _logger.warning(
                    "Could not parse E-Way Bill dates for invoice %s: %s",
                    move.name,
                    e
                )

    def action_update_eway_bill_json(self):
        self.ensure_one()

        l10n_in_edi = self.edi_document_ids.filtered(
            lambda i: i.edi_format_id.code == "in_ewaybill_1_03"
                      and i.state in ("sent", "to_cancel")
        )[:1]

        if not l10n_in_edi:
            raise UserError(_("No E-Way Bill document found."))

        attachment = l10n_in_edi.sudo().attachment_id

        if not attachment:
            raise UserError(_("No E-Way Bill attachment found."))

        try:
            json_data = self._get_l10n_in_edi_ewaybill_response_json()
        except Exception as e:
            raise UserError(_("Unable to read E-Way Bill JSON.\n%s") % str(e))

        json_data.update({
            'EwbNo': int(self.eway_bill_no) if self.eway_bill_no else False,
            'EwbDt': self.eway_bill_date.strftime('%Y-%m-%d 00:00:00')
            if self.eway_bill_date else False,
            'EwbValidTill': self.eway_bill_valid_till.strftime('%Y-%m-%d 23:59:00')
            if self.eway_bill_valid_till else False,
        })

        json_content = json.dumps(json_data, indent=4)

        attachment.sudo().write({
            'datas': base64.b64encode(json_content.encode('utf-8')),
        })

        return True