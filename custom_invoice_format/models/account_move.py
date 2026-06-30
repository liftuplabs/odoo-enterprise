from odoo import models, fields, api, _
from datetime import datetime
import logging
import json
import base64
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

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

    custom_layout_size = fields.Selection([
        ('auto', 'Auto-Fit (Based on lines)'),
        ('normal', 'Normal'),
        ('compact', 'Compact'),
        ('dense', 'Dense (30+ lines)')
    ], string="PDF Layout Size", default='auto', copy=True)

    custom_table_font_size = fields.Selection([
        ('10px', '10px (Small)'),
        ('11px', '11px'),
        ('12px', '12px (Standard)'),
        ('13px', '13px'),
        ('14px', '14px (Large)')
    ], string="Table Font Size", copy=True,
        help="Leave blank to use the layout default.")

    custom_table_font_bold = fields.Boolean(
        string="Bold Table Data", default=False, copy=True,
        help="Make all product rows and totals bold.")

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