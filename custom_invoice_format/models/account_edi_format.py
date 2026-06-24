
import re
import json
from datetime import timedelta
from markupsafe import Markup

from odoo import models, fields, api, _
from odoo.tools import html_escape
from odoo.exceptions import AccessError

import logging

_logger = logging.getLogger(__name__)


class AccountEdiFormatInt(models.Model):
    _inherit = "account.edi.format"

    def _check_move_configuration(self, move):
        _logger.info("---------------- Executing override _check_move_configuration ----------------")
        if self.code != "in_ewaybill_1_03":
            return super()._check_move_configuration(move)
        error_message = []
        base = self._l10n_in_edi_ewaybill_base_irn_or_direct(move)
        if not move.l10n_in_type_id and base == "direct":
            error_message.append(_("- Document Type"))
        if not move.l10n_in_mode:
            error_message.append(_("- Transportation Mode"))
        elif move.l10n_in_mode == "0" and not move.l10n_in_transporter_id:
            error_message.append(_("- Transporter is required when E-waybill is managed by transporter"))
        elif move.l10n_in_mode == "0" and move.l10n_in_transporter_id and not move.l10n_in_transporter_id.vat:
            error_message.append(_("- Selected Transporter is missing GSTIN"))
        elif move.l10n_in_mode == "1":
            if not move.l10n_in_vehicle_no and move.l10n_in_vehicle_type:
                error_message.append(_("- Vehicle Number and Type is required when Transportation Mode is By Road"))
        elif move.l10n_in_mode in ("2", "3", "4"):
            if not move.l10n_in_transportation_doc_no and move.l10n_in_transportation_doc_date:
                error_message.append(_("- Transport document number and date is required when Transportation Mode is Rail,Air or Ship"))
        if error_message:
            error_message.insert(0, _("The following information are missing on the invoice (see eWayBill tab):"))
        goods_lines = move.invoice_line_ids.filtered(lambda line: not (line.display_type in ('line_section', 'line_note', 'rounding') or line.product_id.type == "service"))
        # if not goods_lines:
        #     error_message.append(_('You need at least one product having "Product Type" as stockable or consumable.'))
        if base == "irn":
            # already checked by E-invoice (l10n_in_edi) so no need to check
            return error_message
        is_purchase = move.is_purchase_document(include_receipts=True)
        error_message += self._l10n_in_validate_partner(move.partner_id)
        error_message += self._l10n_in_validate_partner(move.company_id.partner_id, is_company=True)
        if not re.match("^.{1,16}$", is_purchase and move.ref or move.name):
            error_message.append(_("%s number should be set and not more than 16 characters",
                (is_purchase and "Bill Reference" or "Invoice")))
        for line in goods_lines:
            if line.display_type == 'product':
                hsn_code = self._l10n_in_edi_extract_digits(line.l10n_in_hsn_code)
                if not hsn_code:
                    error_message.append(_("HSN code is not set in product line %s", line.name))
                elif not re.match(r'^\d{4}$|^\d{6}$|^\d{8}$', hsn_code):
                    error_message.append(_(
                        "Invalid HSN Code (%(hsn_code)s) in product line %(product_line)s") % {
                        'hsn_code': hsn_code,
                        'product_line': line.product_id.name or line.name
                    })
        if error_message:
            error_message.insert(0, _("Impossible to send the Ewaybill."))
        return error_message

