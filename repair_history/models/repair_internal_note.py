# -*- coding: utf-8 -*-
from odoo import api, Command, fields, models, tools, _
from odoo.exceptions import UserError


class RepairInternalNote(models.Model):
    _name = 'repair.internal.note'
    _description = 'Repair Order Internal Note'
    _order = 'date desc, id desc'

    repair_id = fields.Many2one(
        'repair.order',
        string="Repair Order",
        required=True,
        ondelete='cascade',
        index=True,
    )
    user_id = fields.Many2one(
        'res.users',
        string="Created By",
        default=lambda self: self.env.user,
        readonly=True,
        required=True,
        index=True,
    )
    date = fields.Datetime(
        string="Date & Time",
        default=fields.Datetime.now,
        readonly=True,
        required=True,
        index=True,
    )
    note = fields.Html(
        string="Internal Note",
        required=True,
        sanitize_style=True,
        help="Detailed technical observation, repair note, or internal reference.",
    )
    attachment_ids = fields.Many2many(
        'ir.attachment',
        'repair_internal_note_ir_attachment_rel',
        'note_id',
        'attachment_id',
        string="Attachments",
        help="Attach photos, documents, diagnostic logs, or technical reports.",
    )
    attachment_count = fields.Integer(
        string="Attachment Count",
        compute="_compute_attachment_count",
    )

    @api.depends('attachment_ids')
    def _compute_attachment_count(self):
        for rec in self:
            rec.attachment_count = len(rec.attachment_ids)

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for record in records:
            if record.attachment_ids and record.repair_id:
                # Link attachments to parent repair order for visibility in chatter/documents
                for att in record.attachment_ids:
                    if not att.res_model or att.res_model == self._name:
                        att.write({
                            'res_model': 'repair.order',
                            'res_id': record.repair_id.id,
                        })
        return records


class RepairOrder(models.Model):
    _inherit = 'repair.order'

    internal_note_ids = fields.One2many(
        'repair.internal.note',
        'repair_id',
        string="Internal Notes History",
        copy=False,
    )
    internal_note_count = fields.Integer(
        string="Internal Notes Count",
        compute="_compute_internal_note_count",
    )
    new_internal_note = fields.Html(
        string="New Internal Note",
        help="Enter repair-related notes, observations, or technical details.",
    )
    new_internal_note_attachment_ids = fields.Many2many(
        'ir.attachment',
        'repair_order_new_note_attachment_rel',
        'repair_id',
        'attachment_id',
        string="Attachments",
        help="Upload supporting files or images for the note.",
    )

    @api.depends('internal_note_ids')
    def _compute_internal_note_count(self):
        for rec in self:
            rec.internal_note_count = len(rec.internal_note_ids)

    def action_add_internal_note(self):
        """Creates a new internal note entry in history and clears draft fields."""
        self.ensure_one()
        if not self.new_internal_note or tools.is_html_empty(self.new_internal_note):
            raise UserError(_("Please enter an internal note before saving."))

        self.env['repair.internal.note'].create({
            'repair_id': self.id,
            'note': self.new_internal_note,
            'user_id': self.env.user.id,
            'date': fields.Datetime.now(),
            'attachment_ids': [Command.set(self.new_internal_note_attachment_ids.ids)],
        })

        self.write({
            'new_internal_note': False,
            'new_internal_note_attachment_ids': [Command.clear()],
        })
        return True
