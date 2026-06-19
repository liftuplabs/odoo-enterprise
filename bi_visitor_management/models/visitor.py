# -*- coding: utf-8 -*-
# Part of BrowseInfo. See LICENSE file for full copyright and licensing details.

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class VisitorVisitor(models.Model):
    _name = 'visitor.visitor'
    _description = 'Visitor Details'

    name = fields.Char('Visitor ID', readonly=True,
                       default=lambda self: _('New'))
    visitor_name = fields.Char(string='Name', required=True)
    partner_id = fields.Many2one('res.partner', string='Partner')
    company_name = fields.Char(string='Company Name')
    phone = fields.Char('Phone')
    mobile = fields.Char("Mobile")
    email = fields.Char("Email")
    check_in = fields.Datetime('Check In', required=True)
    check_out = fields.Datetime('Check Out')
    reference = fields.Char('Reference')
    duration = fields.Float(string='Duration(Hours)',
                            compute='_compute_duration', store=True)
    visitor_type_id = fields.Many2one('visitor.type', string='Visitor Type')
    visitor_category_id = fields.Many2one(
        'visitor.category', string='Visitor Category')
    employee_id = fields.Many2one('hr.employee', string='Employee')
    department_id = fields.Many2one(
        'hr.department', string='Department')
    user_id = fields.Many2one(
        'res.users', string='Responsible Person', default=lambda self: self.env.user)
    purpose = fields.Text('Purpose')
    destination_id = fields.Many2one(
        'res.partner', string='Visitor Destination')

    @api.constrains('check_in', 'check_out')
    def _check_dates(self):
        if self.check_in and self.check_out and any(self.filtered(lambda d: d.check_in > d.check_out)):
            raise ValidationError(
                _("Time 'Check In' must be earlier 'Check Out'."))

    @api.depends('check_in', 'check_out')
    def _compute_duration(self):
        for record in self:
            if record.check_in and record.check_out:
                if record.check_in < record.check_out:
                    delta = record.check_out - record.check_in
                    record.duration = delta.total_seconds() / 3600
            else:
                record.duration = 0.0

    @api.onchange('employee_id')
    def onchange_employee_id(self):
        if self.employee_id and self.employee_id.department_id:
            self.department_id = self.employee_id.department_id.id

    @api.onchange('partner_id')
    def onchange_partner_id(self):
        if self.partner_id:
            self.visitor_name = self.partner_id.name
            self.company_name = self.partner_id.parent_id.name
            self.phone = self.partner_id.phone
            self.mobile = self.partner_id.mobile
            self.email = self.partner_id.email

    @api.model_create_multi
    def create(self, vals):
        for val in vals:
            if val.get('name', _('New')) == _('New'):
                val['name'] = self.env['ir.sequence'].next_by_code(
                    'visitor.visitor') or _('New')
        res = super(VisitorVisitor, self).create(val)
        return res

    def action_print_visitor_pass(self):
        mail_template = self.env.ref(
            'bi_visitor_management.email_template_visitor_pass')
        for record in self:
            if mail_template and record.email:
                mail = mail_template.send_mail(int(record.id))
                if mail:
                    mail_id = self.env['mail.mail'].browse(mail)
                    mail_id[0].sudo().send()
